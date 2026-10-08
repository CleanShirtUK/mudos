#include "theme-manager.h"

#include <QGuiApplication>
#include <QQmlEngine>
#include <QQuickView>
#include <QDebug>
#include <QScreen>
#include <QTimer>
#include <QUrl>
#include <QQmlContext>
#include <xcb/xcb.h>

#include <cstdlib>
#include <cstring>

namespace {
xcb_atom_t atom(xcb_connection_t *connection, const char *name)
{
    const auto cookie = xcb_intern_atom(connection, 0, static_cast<uint16_t>(strlen(name)), name);
    auto *reply = xcb_intern_atom_reply(connection, cookie, nullptr);
    if (!reply) return XCB_ATOM_NONE;
    const xcb_atom_t result = reply->atom;
    free(reply);
    return result;
}

void setEwmhDesktopProperties(WId window)
{
    int screenNumber = 0;
    xcb_connection_t *connection = xcb_connect(nullptr, &screenNumber);
    if (!connection) {
        fprintf(stderr, "Desktop wallpaper: could not connect to nested X display\n");
        return;
    }
    if (xcb_connection_has_error(connection)) {
        fprintf(stderr, "Desktop wallpaper: XCB connection error %d\n",
                xcb_connection_has_error(connection));
        xcb_disconnect(connection);
        return;
    }

    const xcb_atom_t windowType = atom(connection, "_NET_WM_WINDOW_TYPE");
    const xcb_atom_t desktop = atom(connection, "_NET_WM_WINDOW_TYPE_DESKTOP");
    const xcb_atom_t state = atom(connection, "_NET_WM_STATE");
    const xcb_atom_t states[] = {
        atom(connection, "_NET_WM_STATE_SKIP_TASKBAR"),
        atom(connection, "_NET_WM_STATE_SKIP_PAGER"),
        atom(connection, "_NET_WM_STATE_BELOW"),
    };
    const auto typeCookie = xcb_change_property_checked(
        connection, XCB_PROP_MODE_REPLACE, static_cast<xcb_window_t>(window), windowType,
        XCB_ATOM_ATOM, 32, 1, &desktop);
    const auto stateCookie = xcb_change_property_checked(
        connection, XCB_PROP_MODE_REPLACE, static_cast<xcb_window_t>(window), state,
        XCB_ATOM_ATOM, 32, 3, states);
    xcb_generic_error_t *error = xcb_request_check(connection, typeCookie);
    if (error) {
        fprintf(stderr, "Desktop wallpaper: setting desktop window type failed (X error %u)\n",
                error->error_code);
        free(error);
    }
    error = xcb_request_check(connection, stateCookie);
    if (error) {
        fprintf(stderr, "Desktop wallpaper: setting desktop window state failed (X error %u)\n",
                error->error_code);
        free(error);
    }
    xcb_disconnect(connection);
}
}

int main(int argc, char **argv)
{
    QGuiApplication application(argc, argv);
    ThemeManager theme(&application);
    fprintf(stderr, "Desktop wallpaper theme: %s; shader: %s\n",
            qPrintable(theme.activeId()), qPrintable(theme.wallpaperShader()));
    QQuickView view;
    view.engine()->rootContext()->setContextProperty("mudosTheme", &theme);
    const QString uiRoot = qEnvironmentVariable("LULU_UI_ROOT", "/opt/lulu/ui");
    view.engine()->addImportPath(uiRoot);
    view.setResizeMode(QQuickView::SizeRootObjectToView);
    view.setFlags(Qt::FramelessWindowHint | Qt::WindowDoesNotAcceptFocus
                  | Qt::WindowStaysOnBottomHint);
    view.setTitle(QStringLiteral("Mudos Desktop Wallpaper"));
    view.setSource(QUrl::fromLocalFile(uiRoot + QStringLiteral("/DesktopWallpaper.qml")));
    if (view.status() == QQuickView::Error) return EXIT_FAILURE;
    const QRect geometry = QGuiApplication::primaryScreen()->geometry();
    view.setGeometry(geometry);
    view.create();
    setEwmhDesktopProperties(view.winId());
    view.show();
    QCoreApplication::processEvents();
    // Openbox normalizes Qt's generic type while first managing the mapped
    // window. Reassert desktop semantics after that initial management pass.
    QTimer::singleShot(250, &view, [&view]() {
        setEwmhDesktopProperties(view.winId());
    });
    QObject::connect(&view, &QQuickView::statusChanged, &application,
                     [&application](QQuickView::Status status) {
        if (status == QQuickView::Error) application.exit(EXIT_FAILURE);
    });
    return application.exec();
}
