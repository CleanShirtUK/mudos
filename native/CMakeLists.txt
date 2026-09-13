cmake_minimum_required(VERSION 3.16)
project(lulu-shell LANGUAGES CXX)
set(CMAKE_AUTOMOC ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(PkgConfig REQUIRED)
find_package(Qt6 REQUIRED COMPONENTS DBus Gui Multimedia Qml Quick)
pkg_check_modules(XCB_XTEST REQUIRED IMPORTED_TARGET xcb-xtest)
pkg_check_modules(XCB_KEYSYMS REQUIRED IMPORTED_TARGET xcb-keysyms)
pkg_check_modules(XCB REQUIRED IMPORTED_TARGET xcb)
pkg_check_modules(SDL3 REQUIRED IMPORTED_TARGET sdl3)

add_executable(lulu-shell lulu-shell.cpp)
target_link_libraries(lulu-shell PRIVATE Qt6::DBus Qt6::Gui Qt6::Multimedia Qt6::Qml Qt6::Quick PkgConfig::XCB PkgConfig::SDL3)

add_executable(mudos-guide mudos-guide.cpp)
target_link_libraries(mudos-guide PRIVATE Qt6::DBus Qt6::Gui Qt6::Qml Qt6::Quick PkgConfig::XCB PkgConfig::XCB_XTEST PkgConfig::XCB_KEYSYMS)

install(TARGETS lulu-shell mudos-guide RUNTIME DESTINATION bin)
