{-# LANGUAGE OverloadedStrings #-}

module DuneWinder.Transpiler.IR
  ( Literal (..)
  , Expr (..)
  , Condition (..)
  , IRNode (..)
  , Routine (..)
  , negated
  ) where

import Data.Text (Text)
import DuneWinder.Transpiler.Types (PLCType, Reg, SegField)

data Literal
  = LitBool Bool
  | LitInt Int
  | LitFloat Double
  | LitString Text
  | LitNone
  deriving (Eq, Show)

data Expr
  = Const Literal PLCType
  | RegExpr Reg
  | SegFieldExpr SegField PLCType
  | BinOp Expr Text Expr PLCType
  | UnaryOp Text Expr PLCType
  | CptCall Text [Expr] PLCType
  deriving (Eq, Show)

data Condition
  = Cmp Text Expr Expr
  | XicCond (Either Reg SegField)
  | XioCond (Either Reg SegField)
  | AndCond [Condition]
  | OrCond [Condition]
  | IsInf Expr
  | IsNotInf Expr
  deriving (Eq, Show)

data IRNode
  = Assign (Either Reg SegField) Expr
  | SetBool Reg Bool
  | If Condition [IRNode] [IRNode]
  | Loop Reg (Either Reg Expr) [IRNode]
  | JSRCall Text [(Reg, Expr)] [(Reg, Reg)]
  | Return (Maybe Expr) (Maybe Reg) Text
  | Fault Reg Text
  | Comment Text
  deriving (Eq, Show)

data Routine = Routine
  { routineName :: Text
  , routineInputs :: [(Text, Reg)]
  , routineOutputs :: [(Text, Reg)]
  , routineBody :: [IRNode]
  , routineAllocComments :: [Text]
  }
  deriving (Eq, Show)

negated :: Condition -> Condition
negated cond =
  case cond of
    Cmp op left right ->
      Cmp
        ( case op of
            "==" -> "!="
            "!=" -> "=="
            "<" -> ">="
            "<=" -> ">"
            ">" -> "<="
            ">=" -> "<"
            _ -> "!="
        )
        left
        right
    XicCond reg -> XioCond reg
    XioCond reg -> XicCond reg
    AndCond parts -> OrCond (map negated parts)
    OrCond parts -> AndCond (map negated parts)
    IsInf expr -> IsNotInf expr
    IsNotInf expr -> IsInf expr
