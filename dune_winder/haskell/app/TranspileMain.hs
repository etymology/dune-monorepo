{-# LANGUAGE OverloadedStrings #-}

module Main where

import Data.Text (Text)
import qualified Data.Text as T
import qualified Data.Text.IO as T
import DuneWinder.Transpiler (transpile)
import System.Environment (getArgs)
import System.Exit (die)
import System.FilePath (takeExtension)

main :: IO ()
main = do
  args <- getArgs
  if null args
    then die "Usage: plc-transpiler-hs <source.py> [more.py ...] [func_name ...]"
    else do
      let (sourcePaths, functionNames) = span ((== ".py") . takeExtension) args
      if null sourcePaths
        then die "No .py source files given."
        else do
          sourceChunks <- mapM (T.readFile) sourcePaths
          let source = T.intercalate "\n" sourceChunks
              requested =
                if null functionNames
                  then Nothing
                  else Just (map T.pack functionNames)
          case transpile source requested of
            Left err -> die (T.unpack err)
            Right out -> T.putStrLn out
