{-# LANGUAGE LambdaCase #-}
{-# LANGUAGE OverloadedStrings #-}

module DuneWinder.Transpiler.Lower
  ( defaultRoutineNameMap
  , defaultFunctionOrder
  , compileModule
  ) where

import Control.Applicative ((<|>))
import Control.Monad (forM)
import Control.Monad.State.Strict
import Data.Foldable (for_)
import Data.Map.Strict (Map)
import qualified Data.Map.Strict as Map
import Data.Maybe (catMaybes, fromMaybe)
import Data.Set (Set)
import qualified Data.Set as Set
import Data.Text (Text)
import qualified Data.Text as T
import DuneWinder.Transpiler.Builtins
import DuneWinder.Transpiler.IR as IR
import qualified DuneWinder.Transpiler.Syntax as Syn
import DuneWinder.Transpiler.RegisterAllocator
import DuneWinder.Transpiler.Types

defaultRoutineNameMap :: Map Text Text
defaultRoutineNameMap =
  Map.fromList
    [ ("cap_segments_speed_by_axis_velocity", "CapSegSpeed")
    , ("_segment_tangent_component_bounds", "SegTangentBounds")
    , ("_max_abs_sin_over_sweep", "MaxAbsSinSweep")
    , ("_max_abs_cos_over_sweep", "MaxAbsCosSweep")
    , ("circle_center_for_segment", "CircleCenterForSeg")
    , ("arc_sweep_rad", "ArcSweepRad")
    ]

defaultFunctionOrder :: [Text]
defaultFunctionOrder =
  [ "_max_abs_sin_over_sweep"
  , "_max_abs_cos_over_sweep"
  , "arc_sweep_rad"
  , "circle_center_for_segment"
  , "_segment_tangent_component_bounds"
  , "cap_segments_speed_by_axis_velocity"
  ]

data CompilerState = CompilerState
  { compilerAlloc :: RegisterAllocator
  , compilerRoutineSigs :: Map Text ([Reg], [Reg])
  , compilerRoutineMap :: Map Text Text
  , compilerModuleConsts :: Map Text Double
  , compilerSegCountVar :: Text
  , compilerRoutines :: [Routine]
  }

data Scope = Scope
  { scopeVars :: Map Text Reg
  , scopeOptionalValid :: Map Text Reg
  , scopeTupleVars :: Map Text [Reg]
  , scopeLoopIdx :: Maybe Reg
  , scopeSegVar :: Maybe Text
  , scopeListVar :: Maybe Text
  , scopeFaultReg :: Maybe Reg
  , scopeEndLabel :: Text
  , scopeRetRegs :: [Reg]
  }

type Compile = State CompilerState
type InScope = StateT Scope Compile

compileModule :: Map Text Syn.FunctionDef -> Maybe [Text] -> Text -> Map Text Double -> [Routine]
compileModule functions requested segCountVar moduleConsts =
  compilerRoutines finalState
  where
    ordered =
      case requested of
        Nothing -> [name | name <- defaultFunctionOrder, Map.member name functions]
        Just names ->
          let requestedSet = Set.fromList names
              known = [name | name <- defaultFunctionOrder, name `Set.member` requestedSet, Map.member name functions]
              extras = [name | name <- names, name `notElem` known, Map.member name functions]
           in known <> extras
    initialState =
      CompilerState
        { compilerAlloc = emptyAllocator
        , compilerRoutineSigs = Map.empty
        , compilerRoutineMap = defaultRoutineNameMap
        , compilerModuleConsts = moduleConsts
        , compilerSegCountVar = segCountVar
        , compilerRoutines = []
        }
    finalState = execState (mapM_ (compileOne functions) ordered) initialState

compileOne :: Map Text Syn.FunctionDef -> Text -> Compile ()
compileOne functions name =
  case Map.lookup name functions of
    Nothing -> pure ()
    Just fn -> do
      routine <- compileFunction fn
      modify' (\s -> s {compilerRoutines = compilerRoutines s <> [routine]})

compileFunction :: Syn.FunctionDef -> Compile Routine
compileFunction fn = do
  routineMap <- gets compilerRoutineMap
  let ldName = Map.findWithDefault (Syn.functionName fn) (Syn.functionName fn) routineMap
      baseScope =
        Scope
          { scopeVars = Map.empty
          , scopeOptionalValid = Map.empty
          , scopeTupleVars = Map.empty
          , scopeLoopIdx = Nothing
          , scopeSegVar = Nothing
          , scopeListVar = Nothing
          , scopeFaultReg = Nothing
          , scopeEndLabel = "lbl_" <> ldName <> "_end"
          , scopeRetRegs = []
          }
  allocBefore <- gets compilerAlloc
  let ((inParams, outParams, body), allocAfter) =
        runState (evalStateT (compileFunctionBody fn) baseScope) allocBefore
  modify' (\s -> s {compilerAlloc = allocAfter})
  let routine =
        Routine
          { routineName = ldName
          , routineInputs = inParams
          , routineOutputs = outParams
          , routineBody = body
          , routineAllocComments = summaryComments allocAfter
          }
  modify' (\s -> s {compilerRoutineSigs = Map.insert (Syn.functionName fn) (map snd inParams, map snd outParams) (compilerRoutineSigs s)})
  pure routine
  where
    compileFunctionBody :: Syn.FunctionDef -> InScope ([(Text, Reg)], [(Text, Reg)], [IRNode])
    compileFunctionBody def = do
      directParams <- fmap catMaybes (mapM allocParam (Syn.functionArgs def))
      extraParams <- handleListParams def
      fault <- liftAlloc BOOL (Syn.functionName def <> "_fault")
      modify' (\scope -> scope {scopeFaultReg = Just fault})
      outParams <- allocReturnRegs def
      body <- fmap concat (mapM convertStmt (Syn.functionBody def))
      pure (extraParams <> directParams, outParams, body)

allocParam :: Syn.ArgDef -> InScope (Maybe (Text, Reg))
allocParam arg = do
  let ann = fromMaybe "" (Syn.argAnnotation arg)
      name = Syn.argName arg
  if ann == "MotionSegment"
    then do
      reg <- liftAlloc IDX (name <> "_idx")
      modify' (\scope -> scope {scopeVars = Map.insert name reg (scopeVars scope), scopeLoopIdx = scopeLoopIdx scope <|> Just reg})
      pure (Just (name <> "_idx", reg))
    else case paramType ann of
      Nothing -> pure Nothing
      Just typ -> do
        reg <- liftAlloc typ name
        modify' (\scope -> scope {scopeVars = Map.insert name reg (scopeVars scope)})
        pure (Just (name, reg))

handleListParams :: Syn.FunctionDef -> InScope [(Text, Reg)]
handleListParams fn =
  fmap concat $
  forM (Syn.functionArgs fn) $ \arg ->
    case fromMaybe "" (Syn.argAnnotation arg) of
      ann
        | "list[" `T.isPrefixOf` ann || "List[" `T.isPrefixOf` ann -> do
            segCountName <- lift (gets compilerSegCountVar)
            reg <- liftAlloc DINT segCountName
            modify' (\scope -> scope {scopeListVar = Just (Syn.argName arg), scopeVars = Map.insert segCountName reg (scopeVars scope)})
            pure [(segCountName, reg)]
        | "Optional[tuple" `T.isPrefixOf` ann -> do
            let base = Syn.argName arg
            rx <- liftAlloc REAL (base <> "_x")
            ry <- liftAlloc REAL (base <> "_y")
            rv <- liftAlloc BOOL (base <> "_valid")
            modify'
              ( \scope ->
                  scope
                    { scopeVars =
                        Map.insert (base <> "_x") rx $
                          Map.insert (base <> "_y") ry $
                            Map.insert base rv (scopeVars scope)
                    , scopeOptionalValid = Map.insert base rv (scopeOptionalValid scope)
                    }
              )
            pure [(base <> "_x", rx), (base <> "_y", ry), (base <> "_valid", rv)]
        | otherwise -> pure []

allocReturnRegs :: Syn.FunctionDef -> InScope [(Text, Reg)]
allocReturnRegs fn =
  case fromMaybe "" (Syn.functionReturn fn) of
    "" -> pure []
    "None" -> pure []
    ann
      | ann == "float" -> do
          reg <- liftAlloc REAL (Syn.functionName fn <> "_ret")
          modify' (\scope -> scope {scopeRetRegs = [reg]})
          pure [("return", reg)]
      | "tuple[float" `T.isPrefixOf` ann -> do
          let count = T.count "float" ann
          regs <- mapM (\ix -> liftAlloc REAL (Syn.functionName fn <> "_ret_" <> tshow ix)) [0 .. count - 1]
          modify' (\scope -> scope {scopeRetRegs = regs})
          pure [("return_" <> tshow ix, reg) | (ix, reg) <- zip [0 :: Int ..] regs]
      | "Optional[float" `T.isPrefixOf` ann -> do
          reg <- liftAlloc REAL (Syn.functionName fn <> "_ret")
          valid <- liftAlloc BOOL (Syn.functionName fn <> "_ret_valid")
          modify' (\scope -> scope {scopeRetRegs = [reg], scopeOptionalValid = Map.insert "_return" valid (scopeOptionalValid scope)})
          pure [("return", reg), ("return_valid", valid)]
      | otherwise -> pure []

convertStmt :: Syn.Stmt -> InScope [IRNode]
convertStmt = \case
  Syn.ReturnStmt value -> convertReturn value
  Syn.RaiseStmt _ -> do
    faultReg <- gets (fromMaybe (Reg BOOL 0) . scopeFaultReg)
    endLabel <- gets scopeEndLabel
    pure [Fault faultReg endLabel]
  Syn.AssignStmt targets value -> convertAssign targets value
  Syn.AnnAssignStmt target ann value -> convertAnnAssign target ann value
  Syn.AugAssignStmt target op value -> convertAugAssign target op value
  Syn.IfStmt test thenBody elseBody -> do
    cond <- convertTest test
    thenNodes <- fmap concat (mapM convertStmt thenBody)
    elseNodes <- fmap concat (mapM convertStmt elseBody)
    pure [If cond thenNodes elseNodes]
  Syn.ForStmt target iter body -> convertFor target iter body
  Syn.ExprStmt expr -> convertExprStmt expr
  Syn.PassStmt -> pure []

convertExprStmt :: Syn.Expr -> InScope [IRNode]
convertExprStmt expr =
  case expr of
    Syn.Call (Syn.Attr _ "append") [Syn.PosArg inner] ->
      case inner of
        Syn.Call (Syn.Name "replace") args -> convertReplace args
        _ -> pure [Comment ("; unsupported call: " <> renderSynExpr expr)]
    Syn.Call (Syn.Name "replace") args -> convertReplace args
    _ -> pure [Comment ("; unsupported call: " <> renderSynExpr expr)]

convertReturn :: Maybe Syn.Expr -> InScope [IRNode]
convertReturn Nothing = do
  endLabel <- gets scopeEndLabel
  pure [Return Nothing Nothing endLabel]
convertReturn (Just value) = do
  endLabel <- gets scopeEndLabel
  listVar <- gets scopeListVar
  case value of
    Syn.Name name
      | Just name == listVar || name == "out" ->
          pure [Return Nothing Nothing endLabel]
    Syn.TupleLiteral exprs -> do
      regs <- gets scopeRetRegs
      nodes <- fmap catMaybes $
        forM (zip [0 :: Int ..] exprs) $ \(ix, expr) ->
          case drop ix regs of
            reg : _ -> do
              irExpr <- convertExpr expr
              pure (Just (Assign (Left reg) irExpr))
            [] -> pure Nothing
      pure (nodes <> [Return Nothing Nothing endLabel])
    Syn.LiteralExpr Syn.LitNone -> do
      validMap <- gets scopeOptionalValid
      let nodes =
            case Map.lookup "_return" validMap of
              Just reg -> [SetBool reg False]
              Nothing -> []
      pure (nodes <> [Return Nothing Nothing endLabel])
    _ -> do
      expr <- convertExpr value
      regs <- gets scopeRetRegs
      case regs of
        reg : _ -> pure [Assign (Left reg) expr, Return Nothing Nothing endLabel]
        [] -> pure [Return (Just expr) Nothing endLabel]

convertAssign :: [Syn.Target] -> Syn.Expr -> InScope [IRNode]
convertAssign [Syn.TargetTuple targets] (Syn.Call func callArgs) =
  convertTupleUnpack targets func callArgs
convertAssign [Syn.TargetTuple targets] (Syn.Name name) = do
  tupleVars <- gets scopeTupleVars
  case Map.lookup name tupleVars of
    Nothing -> pure []
    Just srcRegs ->
      fmap catMaybes $
        forM (zip targets srcRegs) $ \(target, srcReg) ->
          case target of
            Syn.TargetName destName -> do
              dest <- getOrAlloc destName (regType srcReg)
              pure (Just (Assign (Left dest) (RegExpr srcReg)))
            _ -> pure Nothing
convertAssign targets value@(Syn.Call func callArgs)
  | callName func == "replace" = convertReplace callArgs
  | isKnownRoutine func = do
      case targets of
        [target] -> convertSingleJSR target func callArgs
        _ -> genericAssign
  where
    genericAssign = do
      expr <- convertExpr value
      fmap catMaybes (mapM (assignTarget expr) targets)
convertAssign targets value = do
  expr <- convertExpr value
  fmap catMaybes (mapM (assignTarget expr) targets)

convertAnnAssign :: Syn.Target -> Text -> Syn.Expr -> InScope [IRNode]
convertAnnAssign target ann value
  | "list[" `T.isPrefixOf` ann = pure []
  | otherwise = do
      expr <- convertExpr value
      case target of
        Syn.TargetName name -> do
          reg <- getOrAlloc name (plcTypeFromAnnotation ann)
          pure [Assign (Left reg) expr]
        _ -> pure []

convertAugAssign :: Syn.Target -> Syn.BinOp -> Syn.Expr -> InScope [IRNode]
convertAugAssign target op value = do
  dest <- convertLValue target Nothing
  case dest of
    Nothing -> pure []
    Just place -> do
      right <- convertExpr value
      let left =
            case place of
              Left reg -> RegExpr reg
              Right sf -> SegFieldExpr sf REAL
      pure [Assign place (BinOp left (renderBinOp op) right REAL)]

convertFor :: Syn.Target -> Syn.ForIter -> [Syn.Stmt] -> InScope [IRNode]
convertFor target iter body =
  case iter of
    Syn.ForEnumerate _ -> do
      let (idxName, segName) =
            case target of
              Syn.TargetTuple [Syn.TargetName i, Syn.TargetName s] -> (i, Just s)
              _ -> ("_loop_i", Nothing)
      counter <- liftAlloc IDX idxName
      modify' (\scope -> scope {scopeVars = Map.insert idxName counter (scopeVars scope), scopeLoopIdx = Just counter, scopeSegVar = segName})
      segCountName <- lift (gets compilerSegCountVar)
      limit <- gets (fromMaybe (Reg DINT 0) . Map.lookup segCountName . scopeVars)
      bodyNodes <- fmap concat (mapM convertStmt body)
      modify' (\scope -> scope {scopeLoopIdx = Nothing, scopeSegVar = Nothing})
      pure [Loop counter (Left limit) bodyNodes]
    Syn.ForRange args -> do
      let varName =
            case target of
              Syn.TargetName t -> t
              _ -> "_i"
      counter <- liftAlloc IDX varName
      modify' (\scope -> scope {scopeVars = Map.insert varName counter (scopeVars scope)})
      stopExpr <-
        case args of
          [stop] -> convertExpr stop
          (_start : stop : _) -> convertExpr stop
          _ -> pure (Const (LitInt 0) DINT)
      limitReg <-
        case stopExpr of
          RegExpr reg -> pure reg
          _ -> do
            tmp <- liftAlloc DINT (varName <> "_stop")
            pure tmp
      bodyNodes <- fmap concat (mapM convertStmt body)
      pure [Loop counter (Left limitReg) bodyNodes]

convertTupleUnpack :: [Syn.Target] -> Syn.Expr -> [Syn.CallArg] -> InScope [IRNode]
convertTupleUnpack targets func callArgs = do
  routineMap <- lift (gets compilerRoutineMap)
  routineSigs <- lift (gets compilerRoutineSigs)
  let funcNm = callName func
      ldName = Map.findWithDefault funcNm funcNm routineMap
      (_, calleeOutRegs) = Map.findWithDefault ([], []) funcNm routineSigs
  outRegs <- fmap catMaybes $
    forM targets $ \case
      Syn.TargetName name -> do
        reg <- getOrAlloc name REAL
        pure (Just reg)
      _ -> pure Nothing
  let outArgs =
        [ (if ix < length calleeOutRegs then calleeOutRegs !! ix else Reg REAL (9000 + ix), dest)
        | (ix, dest) <- zip [0 :: Int ..] outRegs
        ]
  jsrInputs <- buildJsrInArgs funcNm callArgs
  pure [JSRCall ldName jsrInputs outArgs]

convertSingleJSR :: Syn.Target -> Syn.Expr -> [Syn.CallArg] -> InScope [IRNode]
convertSingleJSR target func callArgs = do
  routineMap <- lift (gets compilerRoutineMap)
  routineSigs <- lift (gets compilerRoutineSigs)
  let funcNm = callName func
      ldName = Map.findWithDefault funcNm funcNm routineMap
      (_, calleeOutRegs) = Map.findWithDefault ([], []) funcNm routineSigs
  inArgs <- buildJsrInArgs funcNm callArgs
  case target of
    Syn.TargetName name ->
      if null calleeOutRegs
        then pure [JSRCall ldName inArgs []]
        else do
          let valueRegs = filter ((/= BOOL) . regType) calleeOutRegs
              validRegs = filter ((== BOOL) . regType) calleeOutRegs
          outArgs <-
            if length valueRegs == 1
              then do
                dest <- getOrAlloc name (regType (head valueRegs))
                pure [(head valueRegs, dest)]
              else do
                regs <- forM (zip [0 :: Int ..] valueRegs) $ \(ix, src) -> do
                  dest <- getOrAlloc (name <> "_" <> tshow ix) (regType src)
                  pure (src, dest)
                modify' (\scope -> scope {scopeTupleVars = Map.insert name (map snd regs) (scopeTupleVars scope)})
                pure regs
          outArgs' <-
            case validRegs of
              validSrc : _ -> do
                validDest <- liftAlloc BOOL (name <> "_valid")
                modify' (\scope -> scope {scopeOptionalValid = Map.insert name validDest (scopeOptionalValid scope)})
                pure (outArgs <> [(validSrc, validDest)])
              [] -> pure outArgs
          pure [JSRCall ldName inArgs outArgs']
    _ -> pure [JSRCall ldName inArgs []]

convertReplace :: [Syn.CallArg] -> InScope [IRNode]
convertReplace callArgs = fmap catMaybes $
  forM callArgs $ \case
    Syn.KwArg fieldName value ->
      case Map.lookup fieldName replaceFieldMap of
        Nothing -> pure Nothing
        Just plcField -> do
          loopIdx <- gets scopeLoopIdx
          case loopIdx of
            Nothing -> pure Nothing
            Just idx -> do
              expr <- convertExpr value
              pure (Just (Assign (Right (SegField (Right idx) plcField)) expr))
    _ -> pure Nothing

assignTarget :: IR.Expr -> Syn.Target -> InScope (Maybe IRNode)
assignTarget expr target = do
  dest <- convertLValue target (Just expr)
  pure (Assign <$> dest <*> pure expr)

convertLValue :: Syn.Target -> Maybe IR.Expr -> InScope (Maybe (Either Reg SegField))
convertLValue target rhs =
  case target of
    Syn.TargetName name
      | name `Set.member` skipVars -> pure Nothing
      | otherwise -> do
          listVar <- gets scopeListVar
          segVar <- gets scopeSegVar
          if Just name == listVar || Just name == segVar
            then pure Nothing
            else do
              reg <- getOrAlloc name (inferType rhs)
              pure (Just (Left reg))
    Syn.TargetAttr expr attr ->
      pure (Right <$> convertSegAttr (Syn.Attr expr attr))
    Syn.TargetSubscript _ _ -> pure Nothing
    Syn.TargetTuple _ -> pure Nothing

convertExpr :: Syn.Expr -> InScope IR.Expr
convertExpr = \case
  Syn.LiteralExpr lit ->
    pure $
      case lit of
        Syn.LitBool b -> Const (LitBool b) BOOL
        Syn.LitInt n -> Const (LitInt n) DINT
        Syn.LitFloat x -> Const (LitFloat x) REAL
        Syn.LitString txt -> Const (LitString txt) REAL
        Syn.LitNone -> Const LitNone BOOL
  Syn.Name name -> do
    moduleConsts <- lift (gets compilerModuleConsts)
    listVar <- gets scopeListVar
    segVar <- gets scopeSegVar
    loopIdx <- gets scopeLoopIdx
    vars <- gets scopeVars
    optionalValid <- gets scopeOptionalValid
    segCountName <- lift (gets compilerSegCountVar)
    pure $
      case () of
        _
          | Just name == segVar, Just idx <- loopIdx -> RegExpr idx
          | Just name == listVar, Just reg <- Map.lookup segCountName vars -> RegExpr reg
          | Just value <- Map.lookup name constMap -> Const (LitFloat value) REAL
          | Just value <- Map.lookup name moduleConsts ->
              if value == fromIntegral (round value :: Int)
                then Const (LitInt (round value)) DINT
                else Const (LitFloat value) REAL
          | Just reg <- Map.lookup name vars -> RegExpr reg
          | Just reg <- Map.lookup name optionalValid -> RegExpr reg
          | otherwise -> Const (LitFloat 0.0) REAL
  Syn.Attr expr attr -> do
    let qualified = callName (Syn.Attr expr attr)
    case Map.lookup qualified constMap of
      Just value -> pure (Const (LitFloat value) REAL)
      Nothing ->
        case convertSegAttr (Syn.Attr expr attr) of
          Just sf ->
            pure (SegFieldExpr sf (Map.findWithDefault REAL (segFieldName sf) segFieldType))
          Nothing -> pure (Const (LitFloat 0.0) REAL)
  Syn.BinaryExpr left op right -> do
    left' <- convertExpr left
    right' <- convertExpr right
    let typ =
          if exprType left' == DINT && exprType right' == DINT && op `elem` [Syn.Add, Syn.Sub, Syn.Mul]
            then DINT
            else REAL
    pure (BinOp left' (renderBinOp op) right' typ)
  Syn.UnaryExpr op operand -> do
    operand' <- convertExpr operand
    pure $
      case op of
        Syn.Neg -> UnaryOp "-" operand' (exprType operand')
        Syn.Not -> UnaryOp "not" operand' BOOL
  Syn.Call func args -> convertCallExpr func args
  Syn.IfExpr body _ _ -> convertExpr body
  Syn.Subscript (Syn.Name name) index -> do
    vars <- gets scopeVars
    optional <- gets scopeOptionalValid
    let idxVal =
          case index of
            Syn.LiteralExpr (Syn.LitInt n) -> n
            _ -> 0
    pure $
      case Map.lookup name optional of
        Just _ ->
          let suffix = if idxVal == 0 then "_x" else "_y"
           in maybe (Const (LitFloat 0.0) REAL) RegExpr (Map.lookup (name <> suffix) vars)
        Nothing -> Const (LitFloat 0.0) REAL
  Syn.TupleLiteral (first : _) -> convertExpr first
  Syn.TupleLiteral [] -> pure (Const (LitFloat 0.0) REAL)
  _ -> pure (Const (LitFloat 0.0) REAL)

convertCallExpr :: Syn.Expr -> [Syn.CallArg] -> InScope IR.Expr
convertCallExpr func args = do
  let funcNm = callName func
      positional = [expr | Syn.PosArg expr <- args]
  case (funcNm, positional) of
    ("float", [Syn.LiteralExpr (Syn.LitString "inf")]) ->
      pure (Const (LitFloat (1 / 0)) REAL)
    ("float", [expr]) -> convertExpr expr
    _ ->
      case Map.lookup funcNm cptInline of
        Just (tag, retType)
          | tag == "PASSTHRU", [expr] <- positional -> convertExpr expr
          | otherwise -> do
              args' <- mapM convertExpr positional
              pure (CptCall tag args' retType)
        Nothing ->
          case Map.lookup funcNm expandCalls of
            Just tag -> do
              args' <- mapM convertExpr positional
              pure (CptCall tag args' (if tag == "CEIL" then DINT else REAL))
            Nothing ->
              case Map.lookup funcNm constMap of
                Just value -> pure (Const (LitFloat value) REAL)
                Nothing -> pure (RegExpr (Reg REAL 0))

convertSegAttr :: Syn.Expr -> Maybe SegField
convertSegAttr expr =
  case expr of
    Syn.Attr owner attr -> do
      plcField <- Map.lookup attr segAttrMap
      let idx =
            case owner of
              Syn.Subscript _ (Syn.LiteralExpr (Syn.LitInt n)) -> Left n
              Syn.Subscript _ (Syn.Name _) -> Right (Reg DINT 0)
              _ -> Right (Reg IDX 0)
      pure (SegField idx plcField)
    _ -> Nothing

convertTest :: Syn.Expr -> InScope Condition
convertTest = \case
  Syn.CompareExpr left pairs -> convertCompare left pairs
  Syn.BoolExpr Syn.And parts -> AndCond <$> mapM convertTest parts
  Syn.BoolExpr Syn.Or parts -> OrCond <$> mapM convertTest parts
  Syn.UnaryExpr Syn.Not inner -> negated <$> convertTest inner
  Syn.Name name -> do
    vars <- gets scopeVars
    optional <- gets scopeOptionalValid
    pure $
      case Map.lookup name vars <|> Map.lookup name optional of
        Just reg -> XicCond (Left reg)
        Nothing -> Cmp "!=" (Const (LitInt 0) DINT) (Const (LitInt 0) DINT)
  Syn.Call func [Syn.PosArg arg]
    | callName func == "math.isinf" -> IsInf <$> convertExpr arg
  attrExpr@(Syn.Attr _ _) ->
    case convertSegAttr attrExpr of
      Just sf -> pure (XicCond (Right sf))
      Nothing -> pure (Cmp "!=" (Const (LitInt 0) DINT) (Const (LitInt 0) DINT))
  expr -> do
    irExpr <- convertExpr expr
    pure (Cmp "!=" irExpr (Const (LitInt 0) DINT))

convertCompare :: Syn.Expr -> [(Syn.CompareOp, Syn.Expr)] -> InScope Condition
convertCompare left pairs = do
  left' <- convertExpr left
  let go _ [] acc = pure (reverse acc)
      go prev ((op, rhs) : rest) acc = do
        right' <- convertExpr rhs
        let cond =
              case op of
                Syn.Eq -> Cmp "==" prev right'
                Syn.NotEq -> Cmp "!=" prev right'
                Syn.Lt -> Cmp "<" prev right'
                Syn.LtE -> Cmp "<=" prev right'
                Syn.Gt -> Cmp ">" prev right'
                Syn.GtE -> Cmp ">=" prev right'
                Syn.Is -> Cmp "==" prev right'
                Syn.IsNot -> Cmp "!=" prev right'
        go right' rest (cond : acc)
  parts <- go left' pairs []
  pure $
    case parts of
      [single] -> single
      xs -> AndCond xs

buildJsrInArgs :: Text -> [Syn.CallArg] -> InScope [(Reg, IR.Expr)]
buildJsrInArgs funcNm callArgs = do
  routineSigs <- lift (gets compilerRoutineSigs)
  loopIdx <- gets scopeLoopIdx
  segVar <- gets scopeSegVar
  let (inRegs, _) = Map.findWithDefault ([], []) funcNm routineSigs
      positional = [expr | Syn.PosArg expr <- callArgs]
  forM (zip [0 :: Int ..] positional) $ \(ix, argNode) -> do
    expr <-
      case argNode of
        Syn.Name name
          | Just name == segVar, Just idx <- loopIdx -> pure (RegExpr idx)
        _ -> convertExpr argNode
    let destReg = if ix < length inRegs then inRegs !! ix else Reg REAL ix
    pure (destReg, expr)

getOrAlloc :: Text -> PLCType -> InScope Reg
getOrAlloc name typ = do
  vars <- gets scopeVars
  case Map.lookup name vars of
    Just reg -> pure reg
    Nothing -> do
      reg <- liftAlloc typ name
      modify' (\scope -> scope {scopeVars = Map.insert name reg (scopeVars scope)})
      pure reg

liftAlloc :: PLCType -> Text -> InScope Reg
liftAlloc typ name = do
  compiler <- lift get
  let (reg, alloc') = runState (alloc typ name) (compilerAlloc compiler)
  lift (put compiler {compilerAlloc = alloc'})
  pure reg

paramType :: Text -> Maybe PLCType
paramType ann
  | "list[" `T.isPrefixOf` ann = Nothing
  | "List[" `T.isPrefixOf` ann = Nothing
  | "MotionSegment" `T.isInfixOf` ann = Nothing
  | "Optional[tuple" `T.isPrefixOf` ann = Nothing
  | ann == "float" = Just REAL
  | ann == "int" = Just DINT
  | ann == "bool" = Just BOOL
  | otherwise = Just REAL

inferType :: Maybe IR.Expr -> PLCType
inferType = maybe REAL exprType

exprType :: IR.Expr -> PLCType
exprType = \case
  Const _ typ -> typ
  RegExpr reg -> regType reg
  SegFieldExpr _ typ -> typ
  BinOp _ _ _ typ -> typ
  UnaryOp _ _ typ -> typ
  CptCall _ _ typ -> typ

callName :: Syn.Expr -> Text
callName = \case
  Syn.Name name -> name
  Syn.Attr base attr -> callName base <> "." <> attr
  _ -> renderSynExpr

isKnownRoutine :: Syn.Expr -> Bool
isKnownRoutine expr = callName expr `Map.member` defaultRoutineNameMap

renderSynExpr :: Syn.Expr -> Text
renderSynExpr = \case
  Syn.Name name -> name
  Syn.Attr base attr -> renderSynExpr base <> "." <> attr
  _ -> "<expr>"

renderBinOp :: Syn.BinOp -> Text
renderBinOp = \case
  Syn.Add -> "+"
  Syn.Sub -> "-"
  Syn.Mul -> "*"
  Syn.Div -> "/"
  Syn.Mod -> "%"

replaceFieldMap :: Map Text Text
replaceFieldMap =
  Map.fromList
    [ ("speed", "Speed")
    , ("accel", "Accel")
    , ("decel", "Decel")
    , ("jerk_accel", "JerkAccel")
    , ("jerk_decel", "JerkDecel")
    , ("term_type", "TermType")
    ]

skipVars :: Set Text
skipVars = Set.fromList ["out", "start", "center"]

tshow :: Show a => a -> Text
tshow = T.pack . show
