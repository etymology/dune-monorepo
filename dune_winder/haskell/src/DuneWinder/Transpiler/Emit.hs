{-# LANGUAGE LambdaCase #-}
{-# LANGUAGE OverloadedStrings #-}

module DuneWinder.Transpiler.Emit
  ( emitAll
  ) where

import Control.Monad.State.Strict (State, evalState, gets, modify')
import Data.Text (Text)
import qualified Data.Text as T
import DuneWinder.Transpiler.IR
import DuneWinder.Transpiler.Types

data EmitState = EmitState
  { emittedLines :: [Text]
  , nextLabelId :: Int
  , scratchReal :: Int
  , scratchBool :: Int
  , scratchDint :: Int
  }

initialEmitState :: EmitState
initialEmitState =
  EmitState
    { emittedLines = []
    , nextLabelId = 0
    , scratchReal = 900
    , scratchBool = 900
    , scratchDint = 900
    }

emitAll :: [Routine] -> [Text]
emitAll routines =
  evalState (concatMapM emitRoutine routines) initialEmitState

emitRoutine :: Routine -> State EmitState [Text]
emitRoutine routine = do
  before <- gets emittedLines
  modify' (\s -> s {emittedLines = []})
  appendLine ("; " <> T.replicate 60 "=")
  appendLine ("; Routine: " <> routineName routine)
  mapM_ appendLine (routineAllocComments routine)
  if null (routineInputs routine)
    then pure ()
    else appendLine ("; Inputs:  " <> T.intercalate "  " [renderReg reg <> "=" <> name | (name, reg) <- routineInputs routine])
  if null (routineOutputs routine)
    then pure ()
    else appendLine ("; Outputs: " <> T.intercalate "  " [renderReg reg <> "=" <> name | (name, reg) <- routineOutputs routine])
  appendLine ("; " <> T.replicate 60 "=")
  mapM_ (\node -> emitNode node (routineName routine)) (routineBody routine)
  appendLine ("LBL lbl_" <> routineName routine <> "_end")
  linesForRoutine <- gets emittedLines
  modify' (\s -> s {emittedLines = before})
  pure (fixupBareLabels linesForRoutine <> [""])

emitNode :: IRNode -> Text -> State EmitState ()
emitNode node routineNm =
  case node of
    Comment txt -> appendLine txt
    Assign dest expr -> emitAssign dest expr
    SetBool reg value -> appendLine ((if value then "OTL " else "OTU ") <> renderReg reg)
    If cond thenBody elseBody -> emitIf cond thenBody elseBody routineNm
    Loop counter limit body -> emitLoop counter limit body routineNm
    JSRCall routine inArgs outArgs -> emitJSR routine inArgs outArgs
    Return value outReg endLabel -> do
      case (value, outReg) of
        (Just expr, Just reg) -> emitAssign (Left reg) expr
        _ -> pure ()
      appendLine ("JMP " <> endLabel)
    Fault reg endLabel -> do
      appendLine ("OTL " <> renderReg reg)
      appendLine ("JMP " <> endLabel)
  where
    _ignored = routineNm

emitAssign :: Either Reg SegField -> Expr -> State EmitState ()
emitAssign dest expr =
  case expr of
    CptCall "ATAN2" [y, x] _ -> emitAtan2 y x dest
    CptCall "MIN" [a, b] _ -> emitMin a b dest
    CptCall "MAX" [a, b] _ -> emitMax a b dest
    CptCall "CEIL" [x] _ -> emitCeil x dest
    CptCall "TRUNC" [x] _ -> emitTrunc x dest
    BinOp a "%" b _ -> appendLine ("MOD " <> matStr a <> " " <> matStr b <> " " <> renderDest dest)
    _ ->
      case dest of
        Left reg
          | regType reg == BOOL ->
              case expr of
                Const (LitBool True) _ -> appendLine ("OTL " <> renderReg reg)
                Const (LitBool False) _ -> appendLine ("OTU " <> renderReg reg)
                _ -> do
                  let src = exprStr expr
                  appendLine ("XIC " <> src <> " OTL " <> renderReg reg)
                  appendLine ("XIO " <> src <> " OTU " <> renderReg reg)
        _ ->
          case expr of
            Const {} -> appendLine ("MOV " <> exprStr expr <> " " <> renderDest dest)
            RegExpr {} -> appendLine ("MOV " <> exprStr expr <> " " <> renderDest dest)
            SegFieldExpr {} -> appendLine ("MOV " <> exprStr expr <> " " <> renderDest dest)
            _ -> appendLine ("CPT " <> renderDest dest <> " " <> exprStr expr)

emitIf :: Condition -> [IRNode] -> [IRNode] -> Text -> State EmitState ()
emitIf cond thenBody elseBody routineNm = do
  lblElse <- nextLabel "else"
  lblEnd <- nextLabel "end"
  let neg = negated cond
  case neg of
    OrCond parts -> do
      tmp <- allocScratch BOOL
      appendLine ("BST " <> T.intercalate " NXB " (map condStr parts) <> " BND OTL " <> renderReg tmp)
      appendLine ("XIC " <> renderReg tmp <> " JMP " <> lblElse)
    _ ->
      let negStr = condStr neg
       in if T.null negStr
            then appendLine ("JMP " <> lblElse)
            else appendLine (negStr <> " JMP " <> lblElse)
  mapM_ (`emitNode` routineNm) thenBody
  if null elseBody
    then appendLine ("LBL " <> lblElse)
    else do
      appendLine ("JMP " <> lblEnd)
      appendLine ("LBL " <> lblElse)
      mapM_ (`emitNode` routineNm) elseBody
      appendLine ("LBL " <> lblEnd)

emitLoop :: Reg -> Either Reg Expr -> [IRNode] -> Text -> State EmitState ()
emitLoop counter limit body routineNm = do
  lblTop <- nextLabel "loop"
  lblEnd <- nextLabel "loop_end"
  appendLine ("MOV 0 " <> renderReg counter)
  appendLine ("LBL " <> lblTop)
  appendLine ("GEQ " <> renderReg counter <> " " <> either renderReg exprStr limit <> " JMP " <> lblEnd)
  mapM_ (`emitNode` routineNm) body
  appendLine ("ADD " <> renderReg counter <> " 1 " <> renderReg counter)
  appendLine ("JMP " <> lblTop)
  appendLine ("LBL " <> lblEnd)

emitJSR :: Text -> [(Reg, Expr)] -> [(Reg, Reg)] -> State EmitState ()
emitJSR routine inArgs outArgs = do
  mapM_ emitInput inArgs
  appendLine ("JSR " <> routine)
  mapM_ emitOutput outArgs
  where
    emitInput (dest, valueExpr)
      | regType dest == BOOL = do
          let src = matStr valueExpr
          appendLine ("XIC " <> src <> " OTL " <> renderReg dest)
          appendLine ("XIO " <> src <> " OTU " <> renderReg dest)
      | otherwise = appendLine ("MOV " <> matStr valueExpr <> " " <> renderReg dest)
    emitOutput (src, dest)
      | regIndex src >= 9000 = appendLine ("; TODO: copy " <> routine <> "_ret_" <> tshow (regIndex src - 9000) <> " " <> renderReg dest)
      | regType dest == BOOL = do
          appendLine ("XIC " <> renderReg src <> " OTL " <> renderReg dest)
          appendLine ("XIO " <> renderReg src <> " OTU " <> renderReg dest)
      | otherwise = appendLine ("MOV " <> renderReg src <> " " <> renderReg dest)

exprStr :: Expr -> Text
exprStr = \case
  Const lit typ -> renderConst lit typ
  RegExpr reg -> renderReg reg
  SegFieldExpr sf _ -> renderSegField sf
  BinOp left op right _ -> exprStr left <> op <> exprStr right
  UnaryOp "-" operand _ -> "-" <> exprStr operand
  UnaryOp _ operand _ -> "NOT(" <> exprStr operand <> ")"
  CptCall "SQR_HYPOT" [a, b] _ -> "SQR(" <> exprStr a <> "*" <> exprStr a <> "+" <> exprStr b <> "*" <> exprStr b <> ")"
  CptCall func args _ -> func <> "(" <> T.intercalate "," (map exprStr args) <> ")"

matStr :: Expr -> Text
matStr expr =
  case expr of
    Const {} -> exprStr expr
    RegExpr {} -> exprStr expr
    SegFieldExpr {} -> exprStr expr
    CptCall "TRUNC" [x] _ -> exprStr (CptCall "TRUNC" [x] DINT)
    BinOp a "%" b _ -> "MOD(" <> exprStr a <> "," <> exprStr b <> ")"
    _ -> exprStr expr

condStr :: Condition -> Text
condStr = \case
  Cmp op left right -> instr op <> " " <> matStr left <> " " <> matStr right
  XicCond reg -> "XIC " <> either renderReg renderSegField reg
  XioCond reg -> "XIO " <> either renderReg renderSegField reg
  AndCond parts -> T.intercalate " " (map condStr parts)
  OrCond _ -> ""
  IsInf expr -> "GEQ " <> matStr expr <> " 3.4028235E+38"
  IsNotInf expr -> "LES " <> matStr expr <> " 3.4028235E+38"
  where
    instr = \case
      "==" -> "EQU"
      "!=" -> "NEQ"
      "<" -> "LES"
      "<=" -> "LEQ"
      ">" -> "GRT"
      ">=" -> "GEQ"
      other -> other

emitAtan2 :: Expr -> Expr -> Either Reg SegField -> State EmitState ()
emitAtan2 y x dest = do
  lblDone <- nextLabel "atan2_done"
  let yS = matStr y
      xS = matStr x
      destS = renderDest dest
  appendLine ("GRT " <> xS <> " 0.0 CPT " <> destS <> " ATN(" <> yS <> "/" <> xS <> ") JMP " <> lblDone)
  appendLine ("LES " <> xS <> " 0.0 GEQ " <> yS <> " 0.0 CPT " <> destS <> " ATN(" <> yS <> "/" <> xS <> ")+3.14159265358979 JMP " <> lblDone)
  appendLine ("LES " <> xS <> " 0.0 LES " <> yS <> " 0.0 CPT " <> destS <> " ATN(" <> yS <> "/" <> xS <> ")-3.14159265358979 JMP " <> lblDone)
  appendLine ("EQU " <> xS <> " 0.0 GRT " <> yS <> " 0.0 MOV 1.5707963267949 " <> destS <> " JMP " <> lblDone)
  appendLine ("EQU " <> xS <> " 0.0 LES " <> yS <> " 0.0 MOV -1.5707963267949 " <> destS <> " JMP " <> lblDone)
  appendLine ("MOV 0.0 " <> destS)
  appendLine ("LBL " <> lblDone)

emitMin :: Expr -> Expr -> Either Reg SegField -> State EmitState ()
emitMin a b dest = do
  lblA <- nextLabel "min_a"
  lblEnd <- nextLabel "min_end"
  let aS = matStr a
      bS = matStr b
      destS = renderDest dest
  appendLine ("LES " <> aS <> " " <> bS <> " JMP " <> lblA)
  appendLine ("MOV " <> bS <> " " <> destS <> " JMP " <> lblEnd)
  appendLine ("LBL " <> lblA <> " MOV " <> aS <> " " <> destS)
  appendLine ("LBL " <> lblEnd)

emitMax :: Expr -> Expr -> Either Reg SegField -> State EmitState ()
emitMax a b dest = do
  lblA <- nextLabel "max_a"
  lblEnd <- nextLabel "max_end"
  let aS = matStr a
      bS = matStr b
      destS = renderDest dest
  appendLine ("GRT " <> aS <> " " <> bS <> " JMP " <> lblA)
  appendLine ("MOV " <> bS <> " " <> destS <> " JMP " <> lblEnd)
  appendLine ("LBL " <> lblA <> " MOV " <> aS <> " " <> destS)
  appendLine ("LBL " <> lblEnd)

emitCeil :: Expr -> Either Reg SegField -> State EmitState ()
emitCeil x dest = do
  lblDone <- nextLabel "ceil_done"
  tmpInt <- allocScratch DINT
  tmpFloat <- allocScratch REAL
  let xS = matStr x
      destS = renderDest dest
  appendLine ("TRN " <> xS <> " " <> renderReg tmpInt)
  appendLine ("MOV " <> renderReg tmpInt <> " " <> renderReg tmpFloat)
  appendLine ("GEQ " <> renderReg tmpFloat <> " " <> xS <> " JMP " <> lblDone)
  appendLine ("ADD " <> renderReg tmpInt <> " 1 " <> renderReg tmpInt)
  appendLine ("LBL " <> lblDone)
  appendLine ("MOV " <> renderReg tmpInt <> " " <> destS)

emitTrunc :: Expr -> Either Reg SegField -> State EmitState ()
emitTrunc x dest =
  appendLine ("TRN " <> matStr x <> " " <> renderDest dest)

renderDest :: Either Reg SegField -> Text
renderDest = either renderReg renderSegField

renderConst :: Literal -> PLCType -> Text
renderConst lit typ =
  case lit of
    LitBool True -> "1"
    LitBool False -> "0"
    LitInt n
      | typ == DINT -> tshow n
      | otherwise -> T.pack (show n)
    LitFloat x
      | isInfinite x && x > 0 -> "3.4028235E+38"
      | isInfinite x && x < 0 -> "-3.4028235E+38"
      | otherwise -> normalizeFloat x
    LitString txt -> txt
    LitNone -> "0"

normalizeFloat :: Double -> Text
normalizeFloat x =
  let raw = T.pack (show x)
   in if "e" `T.isInfixOf` T.toLower raw
        then T.pack (showFFloat 10 x)
        else raw

showFFloat :: Int -> Double -> String
showFFloat digits value =
  let raw = show (fromRational (toRational value) :: Double)
   in if '.' `elem` raw then raw else raw <> "." <> replicate digits '0'

appendLine :: Text -> State EmitState ()
appendLine line = modify' (\s -> s {emittedLines = emittedLines s <> [line]})

nextLabel :: Text -> State EmitState Text
nextLabel prefix = do
  n <- gets nextLabelId
  modify' (\s -> s {nextLabelId = n + 1})
  pure ("lbl_" <> prefix <> "_" <> tshow n)

allocScratch :: PLCType -> State EmitState Reg
allocScratch typ =
  case typ of
    REAL -> do
      n <- gets scratchReal
      modify' (\s -> s {scratchReal = n + 1})
      pure (Reg REAL n)
    DINT -> do
      n <- gets scratchDint
      modify' (\s -> s {scratchDint = n + 1})
      pure (Reg DINT n)
    BOOL -> do
      n <- gets scratchBool
      modify' (\s -> s {scratchBool = n + 1})
      pure (Reg BOOL n)
    IDX -> do
      n <- gets scratchDint
      modify' (\s -> s {scratchDint = n + 1})
      pure (Reg IDX n)

fixupBareLabels :: [Text] -> [Text]
fixupBareLabels = go []
  where
    go acc [] = reverse acc
    go acc (line : rest)
      | isBareLabel line =
          let (passed, remaining) = span (\t -> T.null (T.strip t) || ";" `T.isPrefixOf` T.strip t) rest
           in case remaining of
                [] -> go (["LBL " <> labelName line <> " NOP"] <> reverse passed <> acc) []
                nextLine : more
                  | isBareLabel nextLine ->
                      go ([line <> " NOP"] <> reverse passed <> acc) remaining
                  | otherwise ->
                      go ([line <> " " <> nextLine] <> reverse passed <> acc) more
      | otherwise = go (line : acc) rest

    isBareLabel txt = "LBL " `T.isPrefixOf` txt && T.count " " (T.drop 4 txt) == 0
    labelName = T.drop 4

concatMapM :: Monad m => (a -> m [b]) -> [a] -> m [b]
concatMapM _ [] = pure []
concatMapM f (x : xs) = do
  first <- f x
  rest <- concatMapM f xs
  pure (first <> rest)

tshow :: Show a => a -> Text
tshow = T.pack . show
