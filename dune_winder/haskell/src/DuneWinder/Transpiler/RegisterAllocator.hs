{-# LANGUAGE OverloadedStrings #-}

module DuneWinder.Transpiler.RegisterAllocator
  ( RegisterAllocator (..)
  , emptyAllocator
  , alloc
  , allocTemp
  , summaryComments
  ) where

import Control.Monad.State.Strict (State, gets, modify')
import Data.Text (Text)
import qualified Data.Text as T
import DuneWinder.Transpiler.Types (PLCType (..), Reg (..), renderReg)

data RegisterAllocator = RegisterAllocator
  { nextReal :: Int
  , nextDint :: Int
  , nextBool :: Int
  , nextIdx :: Int
  , allocLog :: [(Text, Reg)]
  }
  deriving (Eq, Show)

emptyAllocator :: RegisterAllocator
emptyAllocator =
  RegisterAllocator
    { nextReal = 0
    , nextDint = 0
    , nextBool = 0
    , nextIdx = 0
    , allocLog = []
    }

alloc :: PLCType -> Text -> State RegisterAllocator Reg
alloc typ name = do
  reg <- case typ of
    REAL -> reserve typ nextReal (\s n -> s {nextReal = n + 1})
    DINT -> reserve typ nextDint (\s n -> s {nextDint = n + 1})
    BOOL -> reserve typ nextBool (\s n -> s {nextBool = n + 1})
    IDX -> reserve typ nextIdx (\s n -> s {nextIdx = n + 1})
  if T.null name
    then pure ()
    else modify' (\s -> s {allocLog = allocLog s <> [(name, reg)]})
  pure reg
  where
    reserve regTyp getter setter = do
      idx <- gets getter
      modify' (\s -> setter s idx)
      pure (Reg regTyp idx)

allocTemp :: PLCType -> State RegisterAllocator Reg
allocTemp typ = alloc typ ""

summaryComments :: RegisterAllocator -> [Text]
summaryComments ra =
  "; Register allocation:"
    : [ ";   " <> renderReg reg <> " = " <> name
      | (name, reg) <- allocLog ra
      ]
