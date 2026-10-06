#include <QGuiApplication>
#include <QJsonDocument>
#include <QJsonObject>
#include <qnativeinterface.h>
#include <QQmlApplicationEngine>
#include "theme-manager.h"
#include <QQmlContext>
#include <QQmlPropertyMap>
#include <QQuickWindow>
#include <QSocketNotifier>

#include <xcb/xcb.h>

#include <cstdlib>
#include <cstring>
#include <cerrno>
#include <fcntl.h>
#include <unistd.h>

namespace {

class NotificationWindow final : public QObject
{
public:
    NotificationWindow(QQuickWindow *window, QQmlPropertyMap *model)
        : window_(window), model_(model) {}

    bool prepare()
    {
        window_->setFlag(Qt::WindowTransparentForInput, true);
        window_->setFlag(Qt::Tool, true);
        window_->create();
        if (!window_->winId()) return false;
        window_->show();
        if (!setExternalOverlay()) return false;
        const int flags = ::fcntl(STDIN_FILENO, F_GETFL, 0);
        if (flags < 0 || ::fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK) < 0) return false;
        notifier_ = new QSocketNotifier(STDIN_FILENO, QSocketNotifier::Read, this);
        connect(notifier_, &QSocketNotifier::activated, this, [this]() { readInput(); });
        qInfo().noquote() << "notification presenter ready pid=" << getpid();
        return true;
    }

private:
    bool setExternalOverlay()
    {
        auto *x11 = qGuiApp->nativeInterface<QNativeInterface::QX11Application>();
        if (!x11 || !x11->connection()) return false;
        const auto cookie = xcb_intern_atom(x11->connection(), 0,
                                            sizeof("GAMESCOPE_EXTERNAL_OVERLAY") - 1,
                                            "GAMESCOPE_EXTERNAL_OVERLAY");
        auto *reply = xcb_intern_atom_reply(x11->connection(), cookie, nullptr);
        if (!reply) return false;
        const uint32_t value = 1;
        xcb_change_property(x11->connection(), XCB_PROP_MODE_REPLACE, window_->winId(),
                            reply->atom, XCB_ATOM_CARDINAL, 32, 1, &value);
        free(reply);
        xcb_flush(x11->connection());
        return true;
    }

    void readInput()
    {
        char buffer[4096];
        while (true) {
            const ssize_t count = ::read(STDIN_FILENO, buffer, sizeof(buffer));
            if (count == 0) break;
            if (count < 0) {
                if (errno == EAGAIN || errno == EWOULDBLOCK) break;
                qWarning() << "notification presenter stdin read failed errno=" << errno;
                break;
            }
            input_.append(buffer, count);
        }
        int newline = input_.indexOf('\n');
        while (newline >= 0) {
            const QByteArray line = input_.left(newline).trimmed();
            input_.remove(0, newline + 1);
            QJsonParseError parseError;
            const QJsonObject object = QJsonDocument::fromJson(line, &parseError).object();
            const QString eventId = object.value("event_id").toString();
            if (parseError.error != QJsonParseError::NoError || object.isEmpty()) {
                qWarning().noquote() << "notification parse failed event_id=" << eventId
                                     << "error=" << parseError.errorString();
                newline = input_.indexOf('\n');
                continue;
            }
            qInfo().noquote() << "notification received event_id=" << eventId;
            model_->insert("visible", object.value("visible").toBool(true));
            model_->insert("title", object.value("title").toString());
            model_->insert("body", object.value("body").toString());
            model_->insert("glyph", object.value("glyph").toString());
            qInfo().noquote() << "notification model updated event_id=" << eventId
                              << "visible=" << model_->value("visible").toBool()
                              << "title=" << model_->value("title").toString();
            newline = input_.indexOf('\n');
        }
    }

    QQuickWindow *window_;
    QQmlPropertyMap *model_;
    QSocketNotifier *notifier_ = nullptr;
    QByteArray input_;
};

} // namespace

int main(int argc, char **argv)
{
    QGuiApplication application(argc, argv);
    QQmlPropertyMap model;
    model.insert("visible", false);
    model.insert("title", QString());
    model.insert("body", QString());
    model.insert("glyph", QString());

    QQmlApplicationEngine engine;
    ThemeManager mudosTheme(&application);
    engine.rootContext()->setContextProperty("mudosTheme", &mudosTheme);
    engine.rootContext()->setContextProperty("notificationModel", &model);
    engine.load(QUrl::fromLocalFile(qEnvironmentVariable(
        "LULU_NOTIFICATION_UI_FILE", "/opt/lulu/ui/MudosNotification.qml")));
    if (engine.rootObjects().isEmpty()) return EXIT_FAILURE;
    auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
    if (!window) return EXIT_FAILURE;
    NotificationWindow presenter(window, &model);
    if (!presenter.prepare()) return EXIT_FAILURE;
    return application.exec();
}
