use serde::{Deserialize, Serialize};
use std::borrow::Cow;
use std::fmt;

/// A fully-qualified PLC tag path. Backed by a `Cow` so const tag paths can
/// be authored without heap allocation.
///
/// Tag names are authoritative per `dune_winder/plc/controller_level_tags.json`
/// and the program-level `programTags.json` files; the host treats them as
/// opaque strings — the only structure assumed is what `libplctag` parses.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct TagPath(Cow<'static, str>);

impl TagPath {
    pub const fn from_static(s: &'static str) -> Self {
        TagPath(Cow::Borrowed(s))
    }

    pub fn new(s: impl Into<String>) -> Self {
        TagPath(Cow::Owned(s.into()))
    }

    pub fn as_str(&self) -> &str {
        self.0.as_ref()
    }
}

impl fmt::Display for TagPath {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.0.as_ref())
    }
}

impl From<&'static str> for TagPath {
    fn from(s: &'static str) -> Self {
        TagPath::from_static(s)
    }
}

impl From<String> for TagPath {
    fn from(s: String) -> Self {
        TagPath(Cow::Owned(s))
    }
}
