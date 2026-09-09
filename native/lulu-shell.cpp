#include <QGuiApplication>
#include <qnativeinterface.h>
#include <QQmlApplicationEngine>
#include <QQuickWindow>
#include <QUrl>

#include <xcb/xcb.h>

#include <cstdlib>

namespace {

bool setSteamGame(QQuickWindow *window)
{
    auto *x11 = qGuiApp->nativeInterface<QNativeInterface::QX11Application>();
    if (!x11 || !x11->connection() || !window->winId())
        return false;

    xcb_connection_t *connection = x11->connection();
    const xcb_intern_atom_cookie_t cookie =
        xcb_intern_atom(connection, 0, sizeof("STEAM_GAME") - 1, "STEAM_GAME");
    xcb_intern_atom_reply_t *reply = xcb_intern_atom_reply(connection, cookie, nullptr);
    if (!reply)
        return false;

    const xcb_atom_t atom = reply->atom;
    free(reply);
    const uint32_t appid = 769;
    xcb_change_property(connection, XCB_PROP_MODE_REPLACE, window->winId(), atom,
                        XCB_ATOM_CARDINAL, 32, 1, &appid);
    xcb_flush(connection);
    return true;
}

} // namespace

int main(int argc, char **argv)
{
    QGuiApplication application(argc, argv);
    QQmlApplicationEngine engine;
    const QString qmlPath = qEnvironmentVariable("LULU_UI_FILE", "/opt/lulu/ui/ConsoleShell.qml");
    engine.load(QUrl::fromLocalFile(qmlPath));

    if (engine.rootObjects().isEmpty())
        return EXIT_FAILURE;

    auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
    if (!window)
        return EXIT_FAILURE;

    window->create();
    if (!setSteamGame(window))
        return EXIT_FAILURE;

    window->show();
    return application.exec();
}
