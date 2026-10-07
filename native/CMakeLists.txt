cmake_minimum_required(VERSION 3.16)
project(lulu-shell LANGUAGES CXX)
set(CMAKE_AUTOMOC ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(PkgConfig REQUIRED)
find_package(Qt6 REQUIRED COMPONENTS DBus Gui Network Qml Quick Test WebEngineQuick)
pkg_check_modules(XCB_XTEST REQUIRED IMPORTED_TARGET xcb-xtest)
pkg_check_modules(XCB_KEYSYMS REQUIRED IMPORTED_TARGET xcb-keysyms)
pkg_check_modules(XCB REQUIRED IMPORTED_TARGET xcb)
pkg_check_modules(SDL3 REQUIRED IMPORTED_TARGET sdl3)

add_executable(lulu-shell lulu-shell.cpp catalogue-model.cpp recent-model.cpp mudos-glass-item.cpp theme-manager.cpp)
target_link_libraries(lulu-shell PRIVATE Qt6::DBus Qt6::Gui Qt6::Network Qt6::Qml Qt6::Quick Qt6::WebEngineQuick
    PkgConfig::XCB PkgConfig::XCB_KEYSYMS PkgConfig::SDL3)

enable_testing()
add_executable(catalogue-model-test catalogue-model-test.cpp catalogue-model.cpp recent-model.cpp)
target_link_libraries(catalogue-model-test PRIVATE Qt6::DBus Qt6::Core Qt6::Test)
add_test(NAME catalogue-model-test COMMAND catalogue-model-test)
add_executable(theme-manager-test theme-manager-test.cpp theme-manager.cpp)
target_compile_definitions(theme-manager-test PRIVATE
    THEME_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/../themes")
target_link_libraries(theme-manager-test PRIVATE Qt6::Core Qt6::Gui Qt6::Test)
add_test(NAME theme-manager-test COMMAND theme-manager-test)

add_executable(mudos-guide mudos-guide.cpp theme-manager.cpp)
target_link_libraries(mudos-guide PRIVATE Qt6::DBus Qt6::Gui Qt6::Qml Qt6::Quick PkgConfig::XCB PkgConfig::XCB_XTEST PkgConfig::XCB_KEYSYMS)

install(TARGETS lulu-shell mudos-guide RUNTIME DESTINATION bin)
