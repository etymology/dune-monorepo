//! Capability misuse should fail to compile.

#[test]
fn capability_misuse_does_not_compile() {
    let t = trybuild::TestCases::new();
    t.compile_fail("tests/compile_fail/*.rs");
}
