{-# LANGUAGE LambdaCase #-}
{-# LANGUAGE OverloadedStrings #-}

module PlcRungTransform
  ( transformText
  ) where

import Data.Char (isDigit, isAsciiUpper, isAsciiLower)
import qualified Data.Text as T
import Data.Text (Text)

protectedLParen, protectedRParen, protectedComma :: Char
protectedLParen = '\xFFF0'
protectedRParen = '\xFFF1'
protectedComma  = '\xFFF2'

transformText :: Text -> Text
transformText =
    restoreProtectedFormulaExpression
  . normalizeLines
  . flattenDelimiters
  . quoteCommandArguments
  . protectSpecialCommandArguments
  . transformBracketedConditions

normalizeSpaces :: Text -> Text
normalizeSpaces = T.unwords . T.words

protectFormulaExpression :: Text -> Text
protectFormulaExpression = T.map $ \case
  '(' -> protectedLParen
  ')' -> protectedRParen
  ',' -> protectedComma
  c   -> c

restoreProtectedFormulaExpression :: Text -> Text
restoreProtectedFormulaExpression = T.map $ \case
  c | c == protectedLParen -> '('
  c | c == protectedRParen -> ')'
  c | c == protectedComma  -> ','
  c                        -> c

splitTopLevelCommas :: Text -> [Text]
splitTopLevelCommas = go 0 0 T.empty []
  where
    go _ _ current acc remaining
      | T.null remaining = reverse (current : acc)
    go parenDepth bracketDepth current acc remaining =
      let (c, rest) = (T.head remaining, T.tail remaining)
      in case c of
           ',' | parenDepth == 0 && bracketDepth == 0 ->
             go parenDepth bracketDepth T.empty (current : acc) rest
           '(' -> go (parenDepth + 1) bracketDepth (T.snoc current c) acc rest
           ')' -> go (max 0 (parenDepth - 1)) bracketDepth (T.snoc current c) acc rest
           '[' -> go parenDepth (bracketDepth + 1) (T.snoc current c) acc rest
           ']' -> go parenDepth (max 0 (bracketDepth - 1)) (T.snoc current c) acc rest
           _   -> go parenDepth bracketDepth (T.snoc current c) acc rest

extractBalancedCall :: Text -> Int -> Maybe (Int, Int, Text)
extractBalancedCall txt startIndex =
  case T.findIndex (== '(') (T.drop startIndex txt) of
    Nothing -> Nothing
    Just relOpen ->
      let openIndex = startIndex + relOpen
      in scan (openIndex + 1) 1 >>= \endIndex ->
           Just
             ( openIndex
             , endIndex
             , T.take (endIndex - openIndex - 2) (T.drop (openIndex + 1) txt)
             )
  where
    len = T.length txt

    scan i depth
      | i >= len && depth /= 0 = Nothing
      | depth == 0 = Just i
      | otherwise =
          let c = T.index txt i
              depth' = case c of
                '(' -> depth + 1
                ')' -> depth - 1
                _   -> depth
          in scan (i + 1) depth'

isNumericTerm :: Text -> Bool
isNumericTerm t =
  case T.unpack (T.strip t) of
    "" -> False
    s ->
      let s' = case s of
            ('+':xs) -> xs
            ('-':xs) -> xs
            xs       -> xs
      in isSimpleNumber s'

isSimpleNumber :: String -> Bool
isSimpleNumber s =
  case break (== '.') s of
    ([], []) -> False
    (lhs, []) -> all isDigit lhs
    (lhs, ['.']) -> all isDigit lhs && not (null lhs)
    (lhs, '.':rhs) ->
      ((not (null lhs) && all isDigit lhs) || null lhs)
        && all isDigit rhs
        && not (null rhs || (null lhs && null rhs))
    _ -> False

extractSpecialFormulaCall :: Text -> Maybe (Text, Text)
extractSpecialFormulaCall stripped =
  case extractBalancedCall stripped 0 of
    Just (3, _, argsText) | "CPT(" `T.isPrefixOf` stripped -> Just ("CPT", argsText)
    Just (3, _, argsText) | "CMP(" `T.isPrefixOf` stripped -> Just ("CMP", argsText)
    _ -> Nothing

matchSpecialFormulaCommandAt :: Text -> Int -> Maybe Text
matchSpecialFormulaCommandAt txt i
  | "CPT(" `T.isPrefixOf` remaining = Just "CPT"
  | "CMP(" `T.isPrefixOf` remaining = Just "CMP"
  | otherwise = Nothing
  where
    remaining = T.drop i txt

rewriteSpecialFormulaCall :: Text -> Text -> Text
rewriteSpecialFormulaCall "CMP" argumentsText =
  "CMP(" <> protectFormulaExpression (T.strip argumentsText) <> ")"
rewriteSpecialFormulaCall command argumentsText =
  case splitTopLevelCommas argumentsText of
    firstArg : secondArg : rest ->
      let firstArg' = normalizeSpaces firstArg
          secondArg' = T.strip secondArg
          combined =
            if null rest
              then secondArg'
              else secondArg' <> "," <> T.intercalate "," rest
      in command <> "(" <> firstArg' <> "," <> protectFormulaExpression combined <> ")"
    _ -> command <> "(" <> argumentsText <> ")"

protectSpecialCommandArguments :: Text -> Text
protectSpecialCommandArguments txt = go 0
  where
    len = T.length txt

    go i
      | i >= len = ""
      | otherwise =
          case matchSpecialFormulaCommandAt txt i of
            Nothing -> T.singleton (T.index txt i) <> go (i + 1)
            Just _ ->
              case extractBalancedCall txt i of
                Nothing -> T.singleton (T.index txt i) <> go (i + 1)
                Just (openIndex, endIndex, argumentsText) ->
                  let command = T.take (openIndex - i) (T.drop i txt)
                  in rewriteSpecialFormulaCall command argumentsText <> go endIndex

normalizeConditionTerm :: Text -> Text
normalizeConditionTerm term =
  let stripped = T.strip term
      specialCase =
        case extractSpecialFormulaCall stripped of
          Just ("CMP", argsText) ->
            Just ("CMP " <> protectFormulaExpression (T.strip argsText))
          Just ("CPT", argsText) ->
            case splitTopLevelCommas argsText of
              firstArg : secondArg : rest ->
                let firstArg' = normalizeSpaces firstArg
                    secondArg' = T.strip secondArg
                    combined =
                      if null rest
                        then secondArg'
                        else secondArg' <> "," <> T.intercalate "," rest
                in Just ("CPT " <> firstArg' <> " " <> protectFormulaExpression combined)
              _ -> Nothing
          _ -> Nothing
  in case specialCase of
       Just x -> x
       Nothing ->
         case parseSimpleCommandCall stripped of
           Nothing -> stripped
           Just (command, args) ->
             let args' = filter (not . T.null) (map normalizeSpaces (splitTopLevelCommas args))
             in if null args'
                  then stripped
                  else command <> " " <> T.intercalate " " args'

replaceBracketedConditions :: Text -> Text
replaceBracketedConditions content =
  let conditions =
        [ normalizeConditionTerm part
        | part <- splitTopLevelCommas content
        , not (T.null (T.strip part))
        ]
  in (if null conditions || all isNumericTerm conditions then "[" <> content <> "]" else "BST " <> T.intercalate " NXB " conditions <> " BND ")

transformBracketedConditions :: Text -> Text
transformBracketedConditions txt = go 0
  where
    len = T.length txt

    go i
      | i >= len = ""
      | T.index txt i /= '[' = T.singleton (T.index txt i) <> go (i + 1)
      | otherwise =
          case findMatchingBracket (i + 1) 1 of
            Nothing -> T.singleton (T.index txt i) <> go (i + 1)
            Just endIndex ->
              let inner = T.take (endIndex - i - 2) (T.drop (i + 1) txt)
                  transformedInner = transformBracketedConditions inner
              in replaceBracketedConditions transformedInner <> go endIndex

    findMatchingBracket j depth
      | j >= len && depth /= 0 = Nothing
      | depth == 0 = Just j
      | otherwise =
          let c = T.index txt j
              depth' = case c of
                '[' -> depth + 1
                ']' -> depth - 1
                _   -> depth
          in findMatchingBracket (j + 1) depth'

parseSimpleCommandCall :: Text -> Maybe (Text, Text)
parseSimpleCommandCall t = do
  openIdx <- T.findIndex (== '(') t
  guardText (not (T.null t) && T.last t == ')')
  let command = T.take openIdx t
      args = T.take (T.length t - openIdx - 2) (T.drop (openIdx + 1) t)
  guardText (validCommand command)
  guardText (not (T.any (`elem` ("()\n" :: String)) args))
  Just (command, args)

validCommand :: Text -> Bool
validCommand name =
  case T.uncons name of
    Nothing -> False
    Just (c, cs) -> validStart c && T.all validRest cs
  where
    validStart c = isAsciiAlpha c || c == '_'
    validRest c = isAsciiAlphaNum c || c == '_' || c == '.'

isAsciiAlpha :: Char -> Bool
isAsciiAlpha c = isAsciiUpper c || isAsciiLower c

isAsciiAlphaNum :: Char -> Bool
isAsciiAlphaNum c = isAsciiAlpha c || isDigit c

guardText :: Bool -> Maybe ()
guardText True = Just ()
guardText False = Nothing

quoteSpacedCommandArguments :: Text -> Text
quoteSpacedCommandArguments t =
  case parseSimpleCommandCall t of
    Nothing -> t
    Just (command, _) | command == "CPT" || command == "CMP" -> t
    Just (command, argsText) ->
      let args = splitTopLevelCommas argsText
          normalizeArg a =
            let a' = normalizeSpaces a
            in if T.any (== ' ') a'
                 && not (T.isPrefixOf "\"" a')
                 && not (T.isSuffixOf "\"" a')
                  then "\"" <> a' <> "\""
                  else a'
      in command <> "(" <> T.intercalate "," (map normalizeArg args) <> ")"

quoteCommandArguments :: Text -> Text
quoteCommandArguments txt = go 0
  where
    len = T.length txt

    go i
      | i >= len = ""
      | otherwise =
          case extractBalancedCall txt i of
            Just (_, endIdx, _) ->
              let whole = T.take (endIdx - i) (T.drop i txt)
              in case parseSimpleCommandCall whole of
                   Just _ -> quoteSpacedCommandArguments whole <> go endIdx
                   Nothing -> T.singleton (T.index txt i) <> go (i + 1)
            Nothing -> T.singleton (T.index txt i) <> go (i + 1)

flattenDelimiters :: Text -> Text
flattenDelimiters = T.map $ \case
  '(' -> ' '
  ')' -> ' '
  ',' -> ' '
  ';' -> '\n'
  c   -> c

normalizeLines :: Text -> Text
normalizeLines txt =
  let trailingNewline = T.isSuffixOf "\n" txt
      ls0 = T.splitOn "\n" txt
      ls = if trailingNewline && not (null ls0) then init ls0 else ls0
      normalized = map (T.dropWhile (== ' ') . normalizeSpaces) ls
      body = T.intercalate "\n" normalized
  in if trailingNewline then body <> "\n" else body
