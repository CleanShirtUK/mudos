cmake_minimum_required(VERSION 3.16)
project(lulu-shell LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(PkgConfig REQUIRED)
find_package(Qt6 REQUIRED COMPONENTS Gui Qml Quick)
pkg_check_modules(XCB REQUIRED IMPORTED_TARGET xcb)
pkg_check_modules(SDL3 REQUIRED IMPORTED_TARGET sdl3)

add_executable(lulu-shell lulu-shell.cpp)
target_link_libraries(lulu-shell PRIVATE Qt6::Gui Qt6::Qml Qt6::Quick PkgConfig::XCB PkgConfig::SDL3)

install(TARGETS lulu-shell RUNTIME DESTINATION bin)
