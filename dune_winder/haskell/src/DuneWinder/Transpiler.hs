{-# LANGUAGE OverloadedStrings #-}

module DuneWinder.Transpiler
  ( transpile
  , defaultFunctionOrder
  , defaultRoutineNameMap
  ) where

import Data.Text (Text)
import qualified Data.Text as T
import DuneWinder.Transpiler.Emit (emitAll)
import DuneWinder.Transpiler.Lower (compileModule, defaultFunctionOrder, defaultRoutineNameMap)
import qualified DuneWinder.Transpiler.Syntax as Syntax

transpile :: Text -> Maybe [Text] -> Either Text Text
transpile source requested = do
  parsed <- Syntax.parseModule source
  let selected = compileModule (Syntax.moduleFunctions parsed) requested "seg_count" (Syntax.moduleConsts parsed)
      rendered = emitAll selected
  pure $
    if null selected
      then "; No matching functions found\n"
      else T.intercalate "\n" rendered
