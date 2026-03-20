{-# LANGUAGE OverloadedStrings #-}

module DuneWinder.Transpiler.Builtins
  ( cptInline
  , expandCalls
  , constMap
  , segAttrMap
  , segFieldType
  ) where

import Data.Map.Strict (Map)
import qualified Data.Map.Strict as Map
import Data.Text (Text)
import DuneWinder.Transpiler.Types (PLCType (..))

cptInline :: Map Text (Text, PLCType)
cptInline =
  Map.fromList
    [ ("abs", ("ABS", REAL))
    , ("math.sqrt", ("SQR", REAL))
    , ("math.hypot", ("SQR_HYPOT", REAL))
    , ("math.sin", ("SIN", REAL))
    , ("math.cos", ("COS", REAL))
    , ("math.tan", ("TAN", REAL))
    , ("math.asin", ("ASN", REAL))
    , ("math.acos", ("ACS", REAL))
    , ("math.floor", ("TRUNC", DINT))
    , ("float", ("PASSTHRU", REAL))
    , ("int", ("TRUNC", DINT))
    ]

expandCalls :: Map Text Text
expandCalls =
  Map.fromList
    [ ("math.atan2", "ATAN2")
    , ("math.ceil", "CEIL")
    , ("math.isinf", "ISINF")
    , ("min", "MIN")
    , ("max", "MAX")
    ]

constMap :: Map Text Double
constMap =
  Map.fromList
    [ ("math.pi", 3.14159265358979)
    , ("math.tau", 6.28318530717959)
    , ("math.e", 2.71828182845905)
    , ("math.inf", 1 / 0)
    ]

segAttrMap :: Map Text Text
segAttrMap =
  Map.fromList
    [ ("x", "XY[0]")
    , ("y", "XY[1]")
    , ("speed", "Speed")
    , ("accel", "Accel")
    , ("decel", "Decel")
    , ("jerk_accel", "JerkAccel")
    , ("jerk_decel", "JerkDecel")
    , ("term_type", "TermType")
    , ("seg_type", "SegType")
    , ("seq", "Seq")
    , ("circle_type", "CircleType")
    , ("via_center_x", "ViaCenter[0]")
    , ("via_center_y", "ViaCenter[1]")
    , ("direction", "Direction")
    , ("valid", "Valid")
    ]

segFieldType :: Map Text PLCType
segFieldType =
  Map.fromList
    [ ("XY[0]", REAL)
    , ("XY[1]", REAL)
    , ("Speed", REAL)
    , ("Accel", REAL)
    , ("Decel", REAL)
    , ("JerkAccel", REAL)
    , ("JerkDecel", REAL)
    , ("TermType", DINT)
    , ("SegType", DINT)
    , ("Seq", DINT)
    , ("CircleType", DINT)
    , ("ViaCenter[0]", REAL)
    , ("ViaCenter[1]", REAL)
    , ("Direction", DINT)
    , ("Valid", BOOL)
    ]
