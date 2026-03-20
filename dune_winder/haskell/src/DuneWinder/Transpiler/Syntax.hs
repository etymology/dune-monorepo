{-# LANGUAGE LambdaCase #-}
{-# LANGUAGE OverloadedStrings #-}

module DuneWinder.Transpiler.Syntax
  ( ModuleSyntax (..)
  , FunctionDef (..)
  , ArgDef (..)
  , Stmt (..)
  , Target (..)
  , Expr (..)
  , Literal (..)
  , BoolOp (..)
  , UnaryOp (..)
  , BinOp (..)
  , CompareOp (..)
  , CallArg (..)
  , ForIter (..)
  , parseModule
  ) where

import Control.Applicative (empty)
import Control.Monad (void)
import Data.Functor (($>))
import Data.Foldable (asum)
import Data.Char (isAlphaNum, isDigit, isSpace)
import Data.Either (partitionEithers)
import Data.Map.Strict (Map)
import qualified Data.Map.Strict as Map
import Data.Maybe (catMaybes)
import Data.Text (Text)
import qualified Data.Text as T
import Data.Void (Void)
import Text.Megaparsec
import Text.Megaparsec.Char
import qualified Text.Megaparsec.Char.Lexer as L

type Parser = Parsec Void Text

data ModuleSyntax = ModuleSyntax
  { moduleConsts :: Map Text Double
  , moduleFunctions :: Map Text FunctionDef
  }
  deriving (Eq, Show)

data FunctionDef = FunctionDef
  { functionName :: Text
  , functionArgs :: [ArgDef]
  , functionReturn :: Maybe Text
  , functionBody :: [Stmt]
  }
  deriving (Eq, Show)

data ArgDef = ArgDef
  { argName :: Text
  , argAnnotation :: Maybe Text
  }
  deriving (Eq, Show)

data Stmt
  = ReturnStmt (Maybe Expr)
  | RaiseStmt Expr
  | AssignStmt [Target] Expr
  | AnnAssignStmt Target Text Expr
  | AugAssignStmt Target BinOp Expr
  | IfStmt Expr [Stmt] [Stmt]
  | ForStmt Target ForIter [Stmt]
  | ExprStmt Expr
  | PassStmt
  deriving (Eq, Show)

data Target
  = TargetName Text
  | TargetTuple [Target]
  | TargetAttr Expr Text
  | TargetSubscript Expr Expr
  deriving (Eq, Show)

data ForIter
  = ForEnumerate Expr
  | ForRange [Expr]
  deriving (Eq, Show)

data Expr
  = Name Text
  | Attr Expr Text
  | Call Expr [CallArg]
  | Subscript Expr Expr
  | TupleLiteral [Expr]
  | ListLiteral [Expr]
  | LiteralExpr Literal
  | BinaryExpr Expr BinOp Expr
  | UnaryExpr UnaryOp Expr
  | BoolExpr BoolOp [Expr]
  | CompareExpr Expr [(CompareOp, Expr)]
  | IfExpr Expr Expr Expr
  deriving (Eq, Show)

data Literal
  = LitBool Bool
  | LitInt Int
  | LitFloat Double
  | LitString Text
  | LitNone
  deriving (Eq, Show)

data BoolOp = And | Or deriving (Eq, Show)
data UnaryOp = Not | Neg deriving (Eq, Show)
data BinOp = Add | Sub | Mul | Div | Mod deriving (Eq, Show)
data CompareOp = Eq | NotEq | Lt | LtE | Gt | GtE | Is | IsNot deriving (Eq, Show)

data CallArg
  = PosArg Expr
  | KwArg Text Expr
  deriving (Eq, Show)

data Line = Line
  { lineIndent :: Int
  , lineContent :: Text
  }
  deriving (Eq, Show)

parseModule :: Text -> Either Text ModuleSyntax
parseModule source = do
  let ls = preprocess source
  (defs, leftovers) <- parseTopLevel ls
  if null leftovers
    then pure (buildModule defs)
    else Left ("unexpected top-level input near: " <> lineContent (head leftovers))

data TopLevel
  = TopConst Text Double
  | TopFunction FunctionDef

parseTopLevel :: [Line] -> Either Text ([TopLevel], [Line])
parseTopLevel [] = Right ([], [])
parseTopLevel (ln : rest)
  | lineIndent ln /= 0 = Left ("unexpected indentation: " <> lineContent ln)
  | "def " `T.isPrefixOf` lineContent ln = do
      (fn, remaining) <- parseFunction ln rest
      (others, leftovers) <- parseTopLevel remaining
      pure (TopFunction fn : others, leftovers)
  | otherwise =
      case parseConstLine (lineContent ln) of
        Just pair -> do
          (others, leftovers) <- parseTopLevel rest
          pure (TopConst (fst pair) (snd pair) : others, leftovers)
        Nothing -> parseTopLevel rest

parseFunction :: Line -> [Line] -> Either Text (FunctionDef, [Line])
parseFunction header rest = do
  (name, argsText, returnAnn) <- parseFunctionHeader (lineContent header)
  let bodyIndent = lineIndent header + 2
  (body, remaining) <- parseBlock bodyIndent rest
  pure
    ( FunctionDef
        { functionName = name
        , functionArgs = parseArgs argsText
        , functionReturn = returnAnn
        , functionBody = body
        }
    , remaining
    )

parseBlock :: Int -> [Line] -> Either Text ([Stmt], [Line])
parseBlock _ [] = Right ([], [])
parseBlock indent allLines@(ln : rest)
  | lineIndent ln < indent = Right ([], allLines)
  | lineIndent ln > indent = Left ("unexpected indentation near: " <> lineContent ln)
  | otherwise = do
      (stmt, remaining) <- parseStmt indent ln rest
      (more, leftovers) <- parseBlock indent remaining
      pure (stmt : more, leftovers)

parseStmt :: Int -> Line -> [Line] -> Either Text (Stmt, [Line])
parseStmt indent ln rest
  | content == "pass" = Right (PassStmt, rest)
  | "if " `T.isPrefixOf` content = do
      condText <- stripTrailingColon =<< stripPrefixOrErr "if " content
      condExpr <- parseExprText condText
      (thenBody, remaining) <- parseBlock (indent + 2) rest
      case remaining of
        (elseLn : restAfterElse)
          | lineIndent elseLn == indent && lineContent elseLn == "else:" -> do
              (elseBody, afterElse) <- parseBlock (indent + 2) restAfterElse
              pure (IfStmt condExpr thenBody elseBody, afterElse)
        _ -> pure (IfStmt condExpr thenBody [], remaining)
  | "for " `T.isPrefixOf` content = do
      forText <- stripTrailingColon =<< stripPrefixOrErr "for " content
      (targetText, iterText) <- splitForClause forText
      target <- parseTargetText targetText
      iterExpr <- parseForIterText iterText
      (body, remaining) <- parseBlock (indent + 2) rest
      pure (ForStmt target iterExpr body, remaining)
  | "return" `T.isPrefixOf` content =
      if content == "return"
        then Right (ReturnStmt Nothing, rest)
        else do
          expr <- parseExprText (T.strip (T.drop 6 content))
          Right (ReturnStmt (Just expr), rest)
  | "raise " `T.isPrefixOf` content = do
      expr <- parseExprText (T.strip (T.drop 5 content))
      Right (RaiseStmt expr, rest)
  | otherwise =
      case splitAugAssign content of
        Just (lhs, op, rhs) -> do
          target <- parseTargetText lhs
          expr <- parseExprText rhs
          Right (AugAssignStmt target op expr, rest)
        Nothing ->
          case splitAnnAssign content of
            Just (lhs, ann, rhs) -> do
              target <- parseTargetText lhs
              expr <- parseExprText rhs
              Right (AnnAssignStmt target ann expr, rest)
            Nothing ->
              case splitAssign content of
                Just (lhs, rhs) -> do
                  targets <- traverse parseTargetText (splitTopLevel ',' lhs)
                  expr <- parseExprText rhs
                  Right (AssignStmt targets expr, rest)
                Nothing -> do
                  expr <- parseExprText content
                  Right (ExprStmt expr, rest)
  where
    content = lineContent ln

buildModule :: [TopLevel] -> ModuleSyntax
buildModule defs =
  let (consts, funcs) = partitionEithers (map toEither defs)
   in ModuleSyntax
        { moduleConsts = Map.fromList consts
        , moduleFunctions = Map.fromList [(functionName fn, fn) | fn <- funcs]
        }
  where
    toEither = \case
      TopConst name value -> Left (name, value)
      TopFunction fn -> Right fn

parseConstLine :: Text -> Maybe (Text, Double)
parseConstLine txt = do
  (lhs, rhs) <- splitAssign txt
  guardName lhs
  expr <- either (const Nothing) Just (parseExprText rhs)
  evalNumeric expr >>= \value -> Just (lhs, value)
  where
    guardName name
      | validIdentifier name = Just ()
      | otherwise = Nothing

parseFunctionHeader :: Text -> Either Text (Text, Text, Maybe Text)
parseFunctionHeader txt = do
  rest <- stripPrefixOrErr "def " txt
  let (name, afterName) = T.breakOn "(" rest
  if T.null name || T.null afterName
    then Left ("invalid function header: " <> txt)
    else do
      (argsText, afterArgs) <- breakBalanced '(' ')' afterName
      afterColon <- stripTrailingColon (T.strip afterArgs)
      let returnAnn =
            case T.stripPrefix "->" afterColon of
              Just ann -> Just (T.strip ann)
              Nothing
                | T.null afterColon -> Nothing
                | otherwise -> Nothing
      pure (T.strip name, argsText, returnAnn)

parseArgs :: Text -> [ArgDef]
parseArgs txt =
  [ let (name, ann) = splitAnnotation part
     in ArgDef name ann
  | part <- splitTopLevel ',' txt
  , let trimmed = T.strip part
  , not (T.null trimmed)
  ]

parseForIterText :: Text -> Either Text ForIter
parseForIterText txt =
  case T.strip txt of
    t
      | "enumerate(" `T.isPrefixOf` t -> do
          (inner, _) <- breakBalanced '(' ')' (T.dropWhile (/= '(') t)
          expr <- parseExprText inner
          pure (ForEnumerate expr)
      | "range(" `T.isPrefixOf` t -> do
          (inner, _) <- breakBalanced '(' ')' (T.dropWhile (/= '(') t)
          args <- traverse parseExprText (filter (not . T.null) (map T.strip (splitTopLevel ',' inner)))
          pure (ForRange args)
      | otherwise -> Left ("unsupported for iterator: " <> txt)

parseTargetText :: Text -> Either Text Target
parseTargetText txt =
  case parse (sc *> targetParser <* eof) "<target>" txt of
    Left err -> Left (T.pack (errorBundlePretty err))
    Right out -> Right out

parseExprText :: Text -> Either Text Expr
parseExprText txt =
  case parse (sc *> exprParser <* eof) "<expr>" txt of
    Left err -> Left (T.pack (errorBundlePretty err))
    Right out -> Right out

targetParser :: Parser Target
targetParser = do
  expr <- atomOrTupleTarget
  pure expr
  where
    atomOrTupleTarget =
      parensTarget
        <|> try tupleTarget
        <|> (postfixTarget =<< nameTarget)
    tupleTarget = do
      first <- simpleTarget
      _ <- symbol ","
      rest <- sepBy1 simpleTarget (symbol ",")
      pure (TargetTuple (first : rest))
    parensTarget = do
      _ <- symbol "("
      elems <- sepBy targetParser (symbol ",")
      _ <- symbol ")"
      pure
        ( case elems of
            [single] -> single
            xs -> TargetTuple xs
        )
    simpleTarget = postfixTarget =<< nameTarget
    nameTarget = TargetName <$> identifier
    postfixTarget base =
      choice
        [ do
            _ <- symbol "."
            field <- identifier
            pure (TargetAttr (targetToExpr base) field)
        , do
            _ <- symbol "["
            idx <- exprParser
            _ <- symbol "]"
            pure (TargetSubscript (targetToExpr base) idx)
        , pure base
        ]
    targetToExpr = \case
      TargetName t -> Name t
      TargetAttr e t -> Attr e t
      TargetSubscript e idx -> Subscript e idx
      TargetTuple _ -> Name "_tuple_target"

exprParser :: Parser Expr
exprParser = ifExprParser

ifExprParser :: Parser Expr
ifExprParser = do
  thenExpr <- orExprParser
  optionalElse <- optional $ do
    keyword "if"
    cond <- orExprParser
    keyword "else"
    elseExpr <- ifExprParser
    pure (cond, elseExpr)
  pure $
    case optionalElse of
      Nothing -> thenExpr
      Just (cond, elseExpr) -> IfExpr thenExpr cond elseExpr

orExprParser :: Parser Expr
orExprParser = chainKeyword Or andExprParser "or"

andExprParser :: Parser Expr
andExprParser = chainKeyword And notExprParser "and"

notExprParser :: Parser Expr
notExprParser =
  (keyword "not" *> (UnaryExpr Not <$> notExprParser))
    <|> compareExprParser

compareExprParser :: Parser Expr
compareExprParser = do
  left <- additiveExprParser
  pairs <- many (try comparePair)
  pure $
    case pairs of
      [] -> left
      xs -> CompareExpr left xs

comparePair :: Parser (CompareOp, Expr)
comparePair = do
  op <-
    choice
      [ try (keyword "is" *> keyword "not" $> IsNot)
      , keyword "is" $> Is
      , symbol "==" $> Eq
      , symbol "!=" $> NotEq
      , try (symbol "<=" $> LtE)
      , try (symbol ">=" $> GtE)
      , symbol "<" $> Lt
      , symbol ">" $> Gt
      ]
  rhs <- additiveExprParser
  pure (op, rhs)

additiveExprParser :: Parser Expr
additiveExprParser = chainLeft multiplicativeExprParser addOp
  where
    addOp =
      choice
        [ symbol "+" $> Add
        , symbol "-" $> Sub
        ]

multiplicativeExprParser :: Parser Expr
multiplicativeExprParser = chainLeft unaryExprParser mulOp
  where
    mulOp =
      choice
        [ symbol "*" $> Mul
        , symbol "/" $> Div
        , symbol "%" $> Mod
        ]

unaryExprParser :: Parser Expr
unaryExprParser =
  choice
    [ symbol "-" *> (UnaryExpr Neg <$> unaryExprParser)
    , atomExprParser
    ]

atomExprParser :: Parser Expr
atomExprParser = do
  base <- atomParser
  postfixes base
  where
    postfixes expr =
      choice
        [ do
            _ <- symbol "."
            field <- identifier
            postfixes (Attr expr field)
        , do
            args <- parens (sepBy callArgParser (symbol ","))
            postfixes
              ( Call expr args
              )
        , do
            idx <- brackets exprParser
            postfixes (Subscript expr idx)
        , pure expr
        ]

atomParser :: Parser Expr
atomParser =
  choice
    [ LiteralExpr <$> try floatLiteral
    , LiteralExpr <$> try intLiteral
    , LiteralExpr <$> stringLiteral
    , keyword "True" $> LiteralExpr (LitBool True)
    , keyword "False" $> LiteralExpr (LitBool False)
    , keyword "None" $> LiteralExpr LitNone
    , try tupleOrParens
    , listLiteral
    , Name <$> identifier
    ]

callArgParser :: Parser CallArg
callArgParser =
  try keywordArgParser <|> (PosArg <$> exprParser)
  where
    keywordArgParser = do
      name <- identifier
      _ <- symbol "="
      KwArg name <$> exprParser

tupleOrParens :: Parser Expr
tupleOrParens = do
  _ <- symbol "("
  elems <- sepBy exprParser (symbol ",")
  _ <- symbol ")"
  pure $
    case elems of
      [single] -> single
      xs -> TupleLiteral xs

listLiteral :: Parser Expr
listLiteral = ListLiteral <$> brackets (sepBy exprParser (symbol ","))

parens :: Parser a -> Parser a
parens p = symbol "(" *> p <* symbol ")"

brackets :: Parser a -> Parser a
brackets p = symbol "[" *> p <* symbol "]"

floatLiteral :: Parser Literal
floatLiteral = do
  raw <- lexeme $ do
    sign <- optional (char '-')
    lhs <- some digitChar
    _ <- char '.'
    rhs <- many digitChar
    expPart <- optional exponentParser
    pure $
      maybe "" T.singleton sign
        <> T.pack lhs
        <> "."
        <> T.pack rhs
        <> maybe "" id expPart
  case reads (T.unpack raw) of
    [(value, "")] -> pure (LitFloat value)
    _ -> fail "invalid float literal"

intLiteral :: Parser Literal
intLiteral = do
  raw <- lexeme $ do
    sign <- optional (char '-')
    digits <- some digitChar
    notFollowedBy (char '.')
    pure (maybe "" T.singleton sign <> T.pack digits)
  case reads (T.unpack raw) of
    [(value, "")] -> pure (LitInt value)
    _ -> fail "invalid int literal"

stringLiteral :: Parser Literal
stringLiteral = lexeme $ do
  void (optional (oneOf ("furbFURB" :: String)))
  quote <- char '"' <|> char '\''
  content <- manyTill (stringChar quote) (char quote)
  pure (LitString (T.pack content))
  where
    stringChar quoteChar =
      choice
        [ char '\\' *> anySingle
        , satisfy (/= quoteChar)
        ]

identifier :: Parser Text
identifier = lexeme $ do
  first <- letterChar <|> char '_'
  rest <- many (satisfy (\c -> isAlphaNum c || c == '_'))
  pure (T.pack (first : rest))

keyword :: Text -> Parser ()
keyword kw = lexeme $ string kw *> notFollowedBy (satisfy isIdentChar)
  where
    isIdentChar c = isAlphaNum c || c == '_'

symbol :: Text -> Parser Text
symbol = lexeme . string

lexeme :: Parser a -> Parser a
lexeme p = p <* sc

sc :: Parser ()
sc = L.space space1 empty empty
  where
    space1 = skipMany (char ' ' <|> char '\t')

chainLeft :: Parser Expr -> Parser BinOp -> Parser Expr
chainLeft termP opP = do
  first <- termP
  rest <- many ((,) <$> opP <*> termP)
  pure (foldl (\acc (op, rhs) -> BinaryExpr acc op rhs) first rest)

chainKeyword :: BoolOp -> Parser Expr -> Text -> Parser Expr
chainKeyword op termP kw = do
  first <- termP
  rest <- many (keyword kw *> termP)
  pure $
    case rest of
      [] -> first
      xs -> BoolExpr op (first : xs)

evalNumeric :: Expr -> Maybe Double
evalNumeric = \case
  LiteralExpr (LitInt n) -> Just (fromIntegral n)
  LiteralExpr (LitFloat x) -> Just x
  UnaryExpr Neg expr -> negate <$> evalNumeric expr
  _ -> Nothing

preprocess :: Text -> [Line]
preprocess =
  mapMaybe toLine . T.lines
  where
    mapMaybe f = catMaybes . map f
    toLine raw =
      let trimmedRight = T.dropWhileEnd isSpace raw
          content = T.dropWhile (== ' ') trimmedRight
          indent = T.length trimmedRight - T.length content
       in if T.null content || "#" `T.isPrefixOf` content
            then Nothing
            else Just (Line indent content)

splitAnnotation :: Text -> (Text, Maybe Text)
splitAnnotation part =
  case splitOnceTopLevel ':' part of
    Nothing -> (T.strip part, Nothing)
    Just (lhs, rhs) -> (T.strip lhs, Just (T.strip rhs))

splitAnnAssign :: Text -> Maybe (Text, Text, Text)
splitAnnAssign txt = do
  (lhs, rhs) <- splitAssign txt
  (name, ann) <- splitOnceTopLevel ':' lhs
  pure (T.strip name, T.strip ann, T.strip rhs)

splitAssign :: Text -> Maybe (Text, Text)
splitAssign txt = do
  idx <- findTopLevelAssignment txt
  let lhs = T.take idx txt
      rhs = T.drop (idx + 1) txt
  pure (T.strip lhs, T.strip rhs)

splitAugAssign :: Text -> Maybe (Text, BinOp, Text)
splitAugAssign txt =
  asum
    [ splitOnOp "+=" Add
    , splitOnOp "-=" Sub
    , splitOnOp "*=" Mul
    , splitOnOp "/=" Div
    ]
  where
    splitOnOp needle op = do
      idx <- findTopLevelText needle txt
      pure (T.strip (T.take idx txt), op, T.strip (T.drop (idx + T.length needle) txt))

splitForClause :: Text -> Either Text (Text, Text)
splitForClause txt =
  case findTopLevelText " in " txt of
    Nothing -> Left ("invalid for clause: " <> txt)
    Just idx ->
      pure
        ( T.strip (T.take idx txt)
        , T.strip (T.drop (idx + 4) txt)
        )

stripPrefixOrErr :: Text -> Text -> Either Text Text
stripPrefixOrErr prefix txt =
  maybe (Left ("expected prefix " <> prefix <> " in " <> txt)) Right (T.stripPrefix prefix txt)

stripTrailingColon :: Text -> Either Text Text
stripTrailingColon txt =
  maybe (Left ("expected trailing ':' in " <> txt)) (Right . T.strip) (T.stripSuffix ":" txt)

breakBalanced :: Char -> Char -> Text -> Either Text (Text, Text)
breakBalanced open close txt =
  case T.uncons txt of
    Just (c, rest)
      | c == open -> go 1 T.empty rest
    _ -> Left ("expected balanced delimiter in " <> txt)
  where
    go :: Int -> Text -> Text -> Either Text (Text, Text)
    go _ acc remaining | T.null remaining = Left ("unterminated group in " <> txt)
    go depth acc remaining =
      case T.uncons remaining of
        Nothing -> Left ("unterminated group in " <> txt)
        Just (c, rest)
          | c == open -> go (depth + 1) (T.snoc acc c) rest
          | c == close && depth == 1 -> Right (acc, rest)
          | c == close -> go (depth - 1) (T.snoc acc c) rest
          | otherwise -> go depth (T.snoc acc c) rest

splitTopLevel :: Char -> Text -> [Text]
splitTopLevel delimiter = go 0 0 False False T.empty []
  where
    go _ _ _ _ current acc remaining
      | T.null remaining = reverse (current : acc)
    go parenDepth bracketDepth inSingle inDouble current acc remaining =
      let c = T.head remaining
          rest = T.tail remaining
       in case c of
            '\'' | not inDouble -> go parenDepth bracketDepth (not inSingle) inDouble (T.snoc current c) acc rest
            '"' | not inSingle -> go parenDepth bracketDepth inSingle (not inDouble) (T.snoc current c) acc rest
            _ | inSingle || inDouble -> go parenDepth bracketDepth inSingle inDouble (T.snoc current c) acc rest
            _ | c == delimiter && parenDepth == 0 && bracketDepth == 0 ->
                go parenDepth bracketDepth inSingle inDouble T.empty (current : acc) rest
            '(' -> go (parenDepth + 1) bracketDepth inSingle inDouble (T.snoc current c) acc rest
            ')' -> go (max 0 (parenDepth - 1)) bracketDepth inSingle inDouble (T.snoc current c) acc rest
            '[' -> go parenDepth (bracketDepth + 1) inSingle inDouble (T.snoc current c) acc rest
            ']' -> go parenDepth (max 0 (bracketDepth - 1)) inSingle inDouble (T.snoc current c) acc rest
            _ -> go parenDepth bracketDepth inSingle inDouble (T.snoc current c) acc rest

splitOnceTopLevel :: Char -> Text -> Maybe (Text, Text)
splitOnceTopLevel delimiter txt = do
  idx <- findTopLevelChar delimiter txt
  pure (T.take idx txt, T.drop (idx + 1) txt)

findTopLevelAssignment :: Text -> Maybe Int
findTopLevelAssignment txt = go 0 0 False False 0
  where
    len = T.length txt
    go parenDepth bracketDepth inSingle inDouble idx
      | idx >= len = Nothing
      | otherwise =
          let c = T.index txt idx
              next = if idx + 1 < len then Just (T.index txt (idx + 1)) else Nothing
           in case c of
                '\'' | not inDouble -> go parenDepth bracketDepth (not inSingle) inDouble (idx + 1)
                '"' | not inSingle -> go parenDepth bracketDepth inSingle (not inDouble) (idx + 1)
                _ | inSingle || inDouble -> go parenDepth bracketDepth inSingle inDouble (idx + 1)
                '(' -> go (parenDepth + 1) bracketDepth inSingle inDouble (idx + 1)
                ')' -> go (max 0 (parenDepth - 1)) bracketDepth inSingle inDouble (idx + 1)
                '[' -> go parenDepth (bracketDepth + 1) inSingle inDouble (idx + 1)
                ']' -> go parenDepth (max 0 (bracketDepth - 1)) inSingle inDouble (idx + 1)
                '='
                  | parenDepth == 0
                      && bracketDepth == 0
                      && next /= Just '='
                      && prevChar idx `notElem` ("!<>=:" :: String) ->
                      Just idx
                _ -> go parenDepth bracketDepth inSingle inDouble (idx + 1)
    prevChar idx
      | idx == 0 = '\0'
      | otherwise = T.index txt (idx - 1)

findTopLevelText :: Text -> Text -> Maybe Int
findTopLevelText needle txt = findIndexFrom 0
  where
    len = T.length txt
    needleLen = T.length needle
    findIndexFrom idx
      | idx + needleLen > len = Nothing
      | not (atTopLevel idx) = findIndexFrom (idx + 1)
      | T.take needleLen (T.drop idx txt) == needle = Just idx
      | otherwise = findIndexFrom (idx + 1)
    atTopLevel upto =
      let prefix = T.take upto txt
       in topLevelDepth prefix == (0, 0)

findTopLevelChar :: Char -> Text -> Maybe Int
findTopLevelChar ch txt = findIndexFrom 0 0 0 False False
  where
    len = T.length txt
    findIndexFrom idx parenDepth bracketDepth inSingle inDouble
      | idx >= len = Nothing
      | otherwise =
          let c = T.index txt idx
           in case c of
                '\'' | not inDouble -> findIndexFrom (idx + 1) parenDepth bracketDepth (not inSingle) inDouble
                '"' | not inSingle -> findIndexFrom (idx + 1) parenDepth bracketDepth inSingle (not inDouble)
                _ | inSingle || inDouble -> findIndexFrom (idx + 1) parenDepth bracketDepth inSingle inDouble
                '(' -> findIndexFrom (idx + 1) (parenDepth + 1) bracketDepth inSingle inDouble
                ')' -> findIndexFrom (idx + 1) (max 0 (parenDepth - 1)) bracketDepth inSingle inDouble
                '[' -> findIndexFrom (idx + 1) parenDepth (bracketDepth + 1) inSingle inDouble
                ']' -> findIndexFrom (idx + 1) parenDepth (max 0 (bracketDepth - 1)) inSingle inDouble
                _ | c == ch && parenDepth == 0 && bracketDepth == 0 -> Just idx
                _ -> findIndexFrom (idx + 1) parenDepth bracketDepth inSingle inDouble

topLevelDepth :: Text -> (Int, Int)
topLevelDepth = T.foldl' step (0, 0)
  where
    step (parenDepth, bracketDepth) c =
      case c of
        '(' -> (parenDepth + 1, bracketDepth)
        ')' -> (max 0 (parenDepth - 1), bracketDepth)
        '[' -> (parenDepth, bracketDepth + 1)
        ']' -> (parenDepth, max 0 (bracketDepth - 1))
        _ -> (parenDepth, bracketDepth)

validIdentifier :: Text -> Bool
validIdentifier t =
  case T.uncons t of
    Nothing -> False
    Just (c, cs) ->
      ((c == '_') || ('a' <= c && c <= 'z') || ('A' <= c && c <= 'Z'))
        && T.all (\x -> isAlphaNum x || x == '_') cs

exponentParser :: Parser Text
exponentParser = do
  e <- char 'e' <|> char 'E'
  sign <- optional (char '+' <|> char '-')
  digits <- some digitChar
  pure (T.pack (e : maybe "" pure sign <> digits))
