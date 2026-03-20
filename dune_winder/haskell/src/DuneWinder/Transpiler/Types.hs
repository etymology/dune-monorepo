{-# LANGUAGE OverloadedStrings #-}

module DuneWinder.Transpiler.Types
  ( PLCType (..)
  , Reg (..)
  , SegField (..)
  , renderReg
  , renderSegField
  , plcTypeFromAnnotation
  ) where

import Data.Text (Text)
import qualified Data.Text as T

data PLCType
  = BOOL
  | REAL
  | DINT
  | IDX
  deriving (Eq, Ord, Show)

data Reg = Reg
  { regType :: PLCType
  , regIndex :: Int
  }
  deriving (Eq, Ord, Show)

data SegField = SegField
  { segFieldIndex :: Either Int Reg
  , segFieldName :: Text
  }
  deriving (Eq, Ord, Show)

renderReg :: Reg -> Text
renderReg reg =
  case regType reg of
    REAL -> "REALS[" <> tshow (regIndex reg) <> "]"
    DINT -> "DINTS[" <> tshow (regIndex reg) <> "]"
    IDX -> "idx_" <> tshow (regIndex reg)
    BOOL -> "BOOLS[" <> tshow (regIndex reg) <> "]"

renderSegField :: SegField -> Text
renderSegField sf =
  "SegQueue["
    <> either tshow renderReg (segFieldIndex sf)
    <> "]."
    <> segFieldName sf

plcTypeFromAnnotation :: Text -> PLCType
plcTypeFromAnnotation ann =
  case ann of
    "float" -> REAL
    "REAL" -> REAL
    "int" -> DINT
    "DINT" -> DINT
    "bool" -> BOOL
    "BOOL" -> BOOL
    _ -> REAL

tshow :: Show a => a -> Text
tshow = T.pack . show
