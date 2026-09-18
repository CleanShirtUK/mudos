#include "mudos-overlay-window.h"

#include <QGuiApplication>
#include <QScreen>
#include <qnativeinterface.h>

#include <xcb/xcb.h>

MudosOverlayWindow::MudosOverlayWindow(QWindow *parent)
    : QQuickWindow(parent)
{
    setColor(Qt::transparent);
    setFlags(Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint);
}

bool MudosOverlayWindow::saveDiagnosticFrame(const QString &path)
{
    const QImage image = grabWindow();
    return !image.isNull() && image.save(path);
}

void MudosOverlayWindow::showEvent(QShowEvent *event)
{
    if (auto *screen = QGuiApplication::primaryScreen())
        setGeometry(screen->geometry());
    QQuickWindow::showEvent(event);
    markExternalOverlay();
}

void MudosOverlayWindow::markExternalOverlay()
{
    auto *x11 = qGuiApp->nativeInterface<QNativeInterface::QX11Application>();
    if (!x11 || !x11->connection() || !winId())
        return;
    const char name[] = "GAMESCOPE_EXTERNAL_OVERLAY";
    const auto cookie = xcb_intern_atom(x11->connection(), 0, sizeof(name) - 1, name);
    auto *reply = xcb_intern_atom_reply(x11->connection(), cookie, nullptr);
    if (!reply)
        return;
    const uint32_t value = 1;
    xcb_change_property(x11->connection(), XCB_PROP_MODE_REPLACE, winId(), reply->atom,
                        XCB_ATOM_CARDINAL, 32, 1, &value);
    free(reply);
    xcb_flush(x11->connection());
}
