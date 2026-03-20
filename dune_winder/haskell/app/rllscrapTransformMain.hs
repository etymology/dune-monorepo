module Main where

import qualified Data.Text.IO as T
import PlcRungTransform (transformText)

main :: IO ()
main = T.interact transformText
