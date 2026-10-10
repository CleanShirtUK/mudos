#include <QGuiApplication>
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFileSystemWatcher>
#include <QJsonDocument>
#include <QJsonParseError>
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
        geometryPath_ = QDir(qEnvironmentVariable("XDG_RUNTIME_DIR", "/run/user/958"))
                            .filePath("mudos-status-geometry.json");
        geometryWatcher_ = new QFileSystemWatcher(this);
        const QFileInfo geometryInfo(geometryPath_);
        if (geometryInfo.dir().exists()) geometryWatcher_->addPath(geometryInfo.dir().absolutePath());
        if (geometryInfo.exists()) geometryWatcher_->addPath(geometryPath_);
        connect(geometryWatcher_, &QFileSystemWatcher::directoryChanged,
                this, [this]() { refreshGeometryWatch(); loadGeometry(); });
        connect(geometryWatcher_, &QFileSystemWatcher::fileChanged,
                this, [this]() { refreshGeometryWatch(); loadGeometry(); });
        loadGeometry();
        const int flags = ::fcntl(STDIN_FILENO, F_GETFL, 0);
        if (flags < 0 || ::fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK) < 0) return false;
        notifier_ = new QSocketNotifier(STDIN_FILENO, QSocketNotifier::Read, this);
        connect(notifier_, &QSocketNotifier::activated, this, [this]() { readInput(); });
        qInfo().noquote() << "notification presenter ready pid=" << getpid();
        return true;
    }

private:
    void refreshGeometryWatch()
    {
        const QFileInfo info(geometryPath_);
        const QString directory = info.dir().absolutePath();
        if (!geometryWatcher_->directories().contains(directory) && QDir(directory).exists())
            geometryWatcher_->addPath(directory);
        if (info.exists() && !geometryWatcher_->files().contains(geometryPath_))
            geometryWatcher_->addPath(geometryPath_);
    }

    void loadGeometry()
    {
        QFile file(geometryPath_);
        if (!file.open(QIODevice::ReadOnly)) return; // retain last valid session layout
        QJsonParseError error;
        const auto document = QJsonDocument::fromJson(file.readAll(), &error);
        if (error.error != QJsonParseError::NoError || !document.isObject()) return;
        const QJsonObject object = document.object();
        const QString session = object.value("session_id").toString();
        const QString space = object.value("coordinate_space").toString();
        const double x = object.value("x").toDouble(-1);
        const double y = object.value("y").toDouble(-1);
        const double width = object.value("width").toDouble(0);
        const double height = object.value("height").toDouble(0);
        const double viewportWidth = object.value("viewport_width").toDouble(0);
        const double viewportHeight = object.value("viewport_height").toDouble(0);
        const double displayWidth = object.value("display_width").toDouble(0);
        const double displayHeight = object.value("display_height").toDouble(0);
        const double uiScale = object.value("ui_scale").toDouble(0);
        const double dpr = object.value("device_pixel_ratio").toDouble(0);
        if (session.isEmpty() || space != "shell-logical-top-left" || x < 0 || y < 0
            || width <= 0 || height <= 0 || viewportWidth <= 0 || viewportHeight <= 0
            || displayWidth <= 0 || displayHeight <= 0 || uiScale <= 0 || dpr <= 0
            || x + width > viewportWidth + 1 || y + height > viewportHeight + 1
            || viewportWidth > displayWidth + 1 || viewportHeight > displayHeight + 1)
            return;
        model_->insert("statusRight", (x + width) * displayWidth / viewportWidth);
        model_->insert("statusBottom", (y + height) * displayHeight / viewportHeight);
        model_->insert("displayWidth", displayWidth);
        model_->insert("displayHeight", displayHeight);
        model_->insert("uiScale", uiScale);
        model_->insert("devicePixelRatio", dpr);
        model_->insert("geometrySession", session);
        model_->insert("geometryValid", true);
        qInfo().noquote() << "notification geometry updated session=" << session
                          << "right=" << model_->value("statusRight").toDouble()
                          << "bottom=" << model_->value("statusBottom").toDouble();
    }

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
            if (count == 0) {
                model_->insert("visible", false);
                qInfo() << "notification producer disconnected; hiding and exiting presenter";
                QCoreApplication::quit();
                return;
            }
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
            model_->insert("severity", object.value("severity").toString("info"));
            model_->insert("glyph", object.value("glyph").toString());
            model_->insert("iconName", object.value("iconName").toString());
            model_->insert("duration", object.value("duration").toDouble(4.0));
            qInfo().noquote() << "notification model updated event_id=" << eventId
                              << "visible=" << model_->value("visible").toBool()
                              << "title=" << model_->value("title").toString();
            newline = input_.indexOf('\n');
        }
    }

    QQuickWindow *window_;
    QQmlPropertyMap *model_;
    QSocketNotifier *notifier_ = nullptr;
    QFileSystemWatcher *geometryWatcher_ = nullptr;
    QString geometryPath_;
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
    model.insert("severity", QStringLiteral("info"));
    model.insert("glyph", QString());
    model.insert("iconName", QString());
    model.insert("duration", 4.0);
    model.insert("geometryValid", false);
    model.insert("statusRight", 0.0);
    model.insert("statusBottom", 0.0);
    model.insert("displayWidth", 0.0);
    model.insert("displayHeight", 0.0);
    model.insert("uiScale", 1.0);
    model.insert("devicePixelRatio", 1.0);
    model.insert("geometrySession", QString());

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
