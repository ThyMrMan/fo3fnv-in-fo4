-- F3NVTest.dll: the test instance's control channel (test-only, never shipped).
-- Built on Dear-Modding-FO4/commonlibf4, which ..\build.bat mirrors into
-- lib\commonlibf4 from the tools_ext folder beside the checkout.
-- See: docs/fork/fo4_story_tests.md#instance

includes("lib/commonlibf4")

set_project("F3NVTest")
set_version("1.0.0")
set_languages("c++23")
add_rules("mode.release")
add_defines("COMMONLIB_RUNTIMECOUNT=3")

target("F3NVTest")
    add_rules("commonlibf4.plugin", {
        name = "F3NVTest",
        author = "fo3fnv-in-fo4",
        description = "Test instance control channel"
    })
    add_files("src/**.cpp", "../../common/json.cpp")
    add_includedirs("src", "../../common")
    set_pcxxheader("src/pch.h")
    set_targetdir("../bin")
