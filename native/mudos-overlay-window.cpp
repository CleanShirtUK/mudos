#include "mudos-overlay-window.h"

#include <QGuiApplication>
#include <QScreen>
#include <QSurfaceFormat>
#include <qnativeinterface.h>

#include <xcb/xcb.h>

MudosOverlayWindow::MudosOverlayWindow(QWindow *parent)
    : QQuickWindow(parent)
{
    setObjectName(QStringLiteral("mudosOverlayHostWindow"));
    auto format = QSurfaceFormat::defaultFormat();
    format.setAlphaBufferSize(8);
    setFormat(format);
    setColor(Qt::transparent);
    setFlags(Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint);
    connect(this, &QWindow::visibilityChanged, this, [this](QWindow::Visibility visibility) {
        if (!isVisible()) {
            qInfo() << "GUIDE_WINDOW_CLOSE"
                    << "object=" << this << "objectName=" << objectName()
                    << "title=" << title() << "winId=" << winId()
                    << "visible_after=" << isVisible()
                    << "visibility=" << visibility << "active=" << isActive()
                    << "geometry=" << geometry();
        }
        qInfo() << "GUIDE_WINDOW_STATE"
                << "object=" << this
                << "objectName=" << objectName()
                << "title=" << title()
                << "winId=" << winId()
                << "visible=" << isVisible()
                << "visibility=" << visibility
                << "active=" << isActive()
                << "geometry=" << geometry();
    });
    connect(this, &QWindow::activeChanged, this, [this]() {
        qInfo() << "GUIDE_WINDOW_STATE"
                << "object=" << this
                << "objectName=" << objectName()
                << "winId=" << winId()
                << "visible=" << isVisible()
                << "visibility=" << visibility()
                << "active=" << isActive()
                << "geometry=" << geometry();
    });
}

void MudosOverlayWindow::showEvent(QShowEvent *event)
{
    if (auto *screen = QGuiApplication::primaryScreen())
        setGeometry(screen->geometry());
    QQuickWindow::showEvent(event);
    markExternalOverlay();
    qInfo() << "GUIDE_WINDOW_OPEN"
            << "object=" << this
            << "objectName=" << objectName()
            << "title=" << title()
            << "winId=" << winId()
            << "visible=" << isVisible()
            << "visibility=" << visibility()
            << "active=" << isActive()
            << "geometry=" << geometry();
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
    qInfo() << "GUIDE_WINDOW_EXTERNAL_OVERLAY"
            << "object=" << this << "winId=" << winId()
            << "property=GAMESCOPE_EXTERNAL_OVERLAY" << "value=1";
}
