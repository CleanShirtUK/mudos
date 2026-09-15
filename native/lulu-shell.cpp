#include <QGuiApplication>
#include <QDebug>
#include <QFile>
#include <QDBusConnection>
#include <QDBusInterface>
#include <QDBusMessage>
#include <QDBusVariant>
#include <QProcess>
#include <QQmlContext>
#include <QQmlPropertyMap>
#include <QQmlApplicationEngine>
#include <QQuickWindow>
#include <QSocketNotifier>
#include <QTimer>
#include <qnativeinterface.h>
#include <QUrl>
#include <QHash>
#include <QSet>
#include <QJsonDocument>
#include <QJsonObject>

#include <SDL3/SDL.h>
#include <xcb/xcb.h>

#include <cstdlib>
#include <csignal>
#include <cstring>
#include <string>
#include <unistd.h>
#include <QTextStream>
#include <chrono>
#include "catalogue-model.h"
#include "recent-model.h"

namespace {

void diagnosticMessageHandler(QtMsgType, const QMessageLogContext &, const QString &message)
{
    QFile file("/tmp/lulu-controller-diagnostics.log");
    if (file.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text)) {
        QTextStream stream(&file);
        stream << message << '\n';
    }
}

class ControllerBridge;

class DbusInputRelay final : public QObject
{
    Q_OBJECT

public:
    DbusInputRelay(ControllerBridge *owner, QString compositePath, QObject *parent)
        : QObject(parent), owner_(owner), compositePath_(std::move(compositePath))
    {
    }

    const QString &compositePath() const { return compositePath_; }

public slots:
    void onInputEvent(const QString &event, double value);

private:
    ControllerBridge *owner_;
    QString compositePath_;
};

class ControllerBridge final : public QQmlPropertyMap
{
    Q_OBJECT
    friend class DbusInputRelay;

public:
    explicit ControllerBridge(QQuickWindow *window, QObject *parent = nullptr)
        : QQmlPropertyMap(this, parent), window_(window)
    {
        const bool initialized = SDL_Init(SDL_INIT_GAMEPAD);
        qInfo() << "controller SDL init" << initialized;
        insert("controllerConnected", false);
        insert("controllerIndex", -1);
        insert("controllerIdentity", QString());
        insert("action", QString());
        insert("actionSerial", 0);
        insert("luluPresented", false);
        insert("guideSelection", 0);
        insert("launchOverlayEnabled",
               qEnvironmentVariable("LULU_LAUNCH_OVERLAY_ENABLED", "true")
                   .compare(QStringLiteral("false"), Qt::CaseInsensitive) != 0);
        refreshDbusSubscriptions();
        dbusDiscoveryTimer_.setInterval(500);
        connect(&dbusDiscoveryTimer_, &QTimer::timeout,
                this, &ControllerBridge::refreshDbusSubscriptions);
        dbusDiscoveryTimer_.start();
        if (initialized)
            scanGamepads();
        timer_.setInterval(5);
        connect(&timer_, &QTimer::timeout, this, &ControllerBridge::poll);
        timer_.start();
    }

    ~ControllerBridge() override
    {
        if (presentationConnection_)
            xcb_disconnect(presentationConnection_);
        if (gamepad_)
            SDL_CloseGamepad(gamepad_);
        SDL_QuitSubSystem(SDL_INIT_GAMEPAD);
    }

    void setWindow(QQuickWindow *window)
    {
        window_ = window;
        qInfo() << "controller Lulu window" << window_->winId();
        connect(window_, &QQuickWindow::beforeSynchronizing, this, [this]() {
            timelineEvent("beforeSynchronizing");
            renderFrameStartNs_ = timelineNowNs();
        }, Qt::DirectConnection);
        connect(window_, &QQuickWindow::afterSynchronizing, this, [this]() {
            timelineEvent("afterSynchronizing");
        }, Qt::DirectConnection);
        connect(window_, &QQuickWindow::beforeRendering, this, [this]() {
            timelineEvent("beforeRendering");
        }, Qt::DirectConnection);
        connect(window_, &QQuickWindow::afterRendering, this, [this]() {
            maybeArmTimeline();
            if (renderTimelineFrames_ > 0) {
                const qint64 now = timelineNowNs();
                qInfo() << "RENDER_TIMELINE" << "afterRendering"
                        << "mono_ns=" << now
                        << "frame_ns=" << (renderFrameStartNs_ > 0 ? now - renderFrameStartNs_ : 0)
                        << "remaining=" << renderTimelineFrames_;
                --renderTimelineFrames_;
            }
        }, Qt::DirectConnection);
        setupPresentationObserver();
    }

    Q_INVOKABLE QString consumeDiagnosticRefreshRequest()
    {
        const QString path = QStringLiteral("/tmp/lulu-qml-refresh-request");
        if (!QFile::exists(path))
            return {};
        QFile file(path);
        QString group;
        if (file.open(QIODevice::ReadOnly | QIODevice::Text))
            group = QString::fromUtf8(file.readAll()).trimmed();
        file.close();
        QFile::remove(path);
        return group.isEmpty() ? QStringLiteral("all") : group;
    }

private slots:
    void onDbusInputEvent(const QString &compositePath, const QString &event, double value)
    {
        handleInputEvent(compositePath, event, value);
    }

private:
    static qint64 timelineNowNs()
    {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count();
    }

    void maybeArmTimeline()
    {
        if (renderTimelineFrames_ <= 0 && QFile::exists("/tmp/lulu-render-timeline-arm")) {
            QFile::remove("/tmp/lulu-render-timeline-arm");
            renderTimelineFrames_ = 180;
            qInfo() << "RENDER_TIMELINE armed mono_ns=" << timelineNowNs();
        }
    }

    void timelineEvent(const char *event)
    {
        maybeArmTimeline();
        if (renderTimelineFrames_ > 0)
            qInfo() << "RENDER_TIMELINE" << event
                    << "mono_ns=" << timelineNowNs()
                    << "remaining=" << renderTimelineFrames_;
    }

    static constexpr const char *inputService = "org.shadowblip.InputPlumber";
    static constexpr const char *inputInterface = "org.shadowblip.Input.CompositeDevice";

    bool setInterceptMode(const QString &compositePath, uint mode)
    {
        QDBusMessage message = QDBusMessage::createMethodCall(
            inputService, compositePath, "org.freedesktop.DBus.Properties", "Set");
        message << QString::fromLatin1(inputInterface) << QStringLiteral("InterceptMode")
                << QVariant::fromValue(QDBusVariant(QVariant::fromValue(mode)));
        const auto reply = QDBusConnection::systemBus().call(message);
        if (reply.type() == QDBusMessage::ErrorMessage) {
            qWarning() << "InputPlumber mode change failed" << reply.errorMessage();
            return false;
        }
        return true;
    }

    void clearTarget()
    {
        targetWindow_ = XCB_WINDOW_NONE;
        targetPid_ = 0;
    }

    void restoreInput()
    {
        if (!guideOwnerComposite_.isEmpty())
            setInterceptMode(guideOwnerComposite_, 1);
        guideOwnerComposite_.clear();
        clearTarget();
    }

    void handleInputEvent(const QString &compositePath, const QString &event, double value)
    {
        if (value != 1.0)
            return;
        if (event == QStringLiteral("ui_guide") && !guideProcess_) {
            guideOwnerComposite_ = compositePath;
            startGuide();
            return;
        }
        if (guideProcess_ && compositePath == guideOwnerComposite_
            && (event == QStringLiteral("ui_guide")
                              || event == QStringLiteral("ui_up")
                              || event == QStringLiteral("ui_down")
                              || event == QStringLiteral("ui_accept")
                              || event == QStringLiteral("ui_back"))) {
            guideProcess_->write(event.toUtf8() + '\n');
        }
    }

    void finishGuide()
    {
        if (guideProcess_) {
            guideProcess_->deleteLater();
            guideProcess_ = nullptr;
        }
        restoreInput();
    }

    bool startGuide()
    {
        if (guideProcess_ || !presentationConnection_ || !focusedWindow_ || !window_) {
            restoreInput();
            return false;
        }
        targetWindow_ = focusedWindow_;
        targetPid_ = windowProperty(targetWindow_, "_NET_WM_PID");
        guideProcess_ = new QProcess(this);
        const auto menuCommand = providerMenuCommand(targetPid_);
        const auto menuLabel = providerMenuLabel(targetPid_);
        qInfo() << "Guide context" << "pid=" << targetPid_
                << "command=" << menuCommand << "label=" << menuLabel;
        connect(guideProcess_, &QProcess::readyReadStandardOutput, this, [this]() {
            qInfo().noquote() << guideProcess_->readAllStandardOutput().trimmed();
        });
        connect(guideProcess_, &QProcess::readyReadStandardError, this, [this]() {
            qWarning().noquote() << guideProcess_->readAllStandardError().trimmed();
        });
        connect(guideProcess_, &QProcess::finished, this,
                [this](int, QProcess::ExitStatus) { finishGuide(); });
        guideProcess_->start("/opt/lulu/bin/mudos-guide", {
            QString::number(targetWindow_), QString::number(targetPid_), menuCommand, menuLabel
        });
        if (!guideProcess_->waitForStarted(1000)) {
            finishGuide();
            return false;
        }
        return true;
    }

    void refreshDbusSubscriptions()
    {
        QDBusInterface manager(inputService,
                               "/org/shadowblip/InputPlumber/Manager",
                               "org.shadowblip.InputManager",
                               QDBusConnection::systemBus());
        const QStringList composites = manager.property("GamepadOrder").toStringList();
        QSet<QString> discovered;
        for (const QString &compositePath : composites) {
            QDBusInterface composite(inputService, compositePath,
                                     "org.shadowblip.Input.CompositeDevice",
                                     QDBusConnection::systemBus());
            for (const QString &dbusPath : composite.property("DbusDevices").toStringList()) {
                discovered.insert(dbusPath);
                if (dbusRelays_.contains(dbusPath))
                    continue;
                auto *relay = new DbusInputRelay(this, compositePath, this);
                dbusRelays_.insert(dbusPath, relay);
                QDBusConnection::systemBus().connect(
                    inputService, dbusPath, dbusInterface, "InputEvent",
                    relay, SLOT(onInputEvent(QString,double)));
                qInfo() << "subscribed InputPlumber D-Bus target"
                        << dbusPath << "composite=" << compositePath;
            }
        }
        for (auto iterator = dbusRelays_.begin(); iterator != dbusRelays_.end();) {
            if (discovered.contains(iterator.key())) {
                ++iterator;
                continue;
            }
            QDBusConnection::systemBus().disconnect(
                inputService, iterator.key(), dbusInterface, "InputEvent",
                iterator.value(), SLOT(onInputEvent(QString,double)));
            iterator.value()->deleteLater();
            iterator = dbusRelays_.erase(iterator);
        }
    }

    QString providerMenuCommand(uint32_t pid) const
    {
        QFile environment(QStringLiteral("/proc/%1/environ").arg(pid));
        if (environment.open(QIODevice::ReadOnly)) {
            const auto entries = environment.readAll().split('\0');
            for (const auto &entry : entries) {
                const QByteArray prefix("MUDOS_PROVIDER_MENU_COMMAND=");
                if (entry.startsWith(prefix))
                    return QString::fromUtf8(entry.mid(prefix.size()));
            }
        }
        QDBusInterface sessiond("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession",
                                "org.lulu.ConsoleSession", QDBusConnection::sessionBus());
        const auto reply = sessiond.call("GetState");
        if (reply.type() != QDBusMessage::ErrorMessage && !reply.arguments().isEmpty()) {
            const auto state = QJsonDocument::fromJson(
                reply.arguments().constFirst().toString().toUtf8()).object();
            if (state.value("primary_id").toString() == QStringLiteral("steam-store"))
                return QStringLiteral("steam");
        }
        return {};
    }

    QString providerMenuLabel(uint32_t pid) const
    {
        QDBusInterface sessiond("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession",
                                "org.lulu.ConsoleSession", QDBusConnection::sessionBus());
        const auto reply = sessiond.call("GetState");
        if (reply.type() != QDBusMessage::ErrorMessage && !reply.arguments().isEmpty()) {
            const auto state = QJsonDocument::fromJson(
                reply.arguments().constFirst().toString().toUtf8()).object();
            if (state.value("primary_id").toString() == QStringLiteral("steam-store"))
                return state.value("delegated_surface").toString() == QStringLiteral("downloads")
                    ? QStringLiteral("Go to Store") : QStringLiteral("View Download Queue");
        }
        return QStringLiteral("Provider Menu");
    }

    void scanGamepads()
    {
        int count = 0;
        SDL_JoystickID *ids = SDL_GetGamepads(&count);
        qInfo() << "SDL gamepad scan count=" << count;
        if (ids && count > 0) {
            gamepad_ = SDL_OpenGamepad(ids[0]);
            if (gamepad_) {
                qInfo() << "SDL gamepad opened" << SDL_GetGamepadName(gamepad_);
                insert("controllerConnected", true);
                insert("controllerIndex", 1);
                insert("controllerIdentity", QString::fromUtf8(SDL_GetGamepadName(gamepad_)));
            }
        }
        SDL_free(ids);
    }

    void poll()
    {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_GAMEPAD_ADDED && !gamepad_) {
                gamepad_ = SDL_OpenGamepad(event.gdevice.which);
                if (gamepad_) {
                    insert("controllerConnected", true);
                    insert("controllerIndex", 1);
                    insert("controllerIdentity", QString::fromUtf8(SDL_GetGamepadName(gamepad_)));
                }
            } else if (event.type == SDL_EVENT_GAMEPAD_REMOVED && gamepad_
                       && event.gdevice.which == SDL_GetGamepadID(gamepad_)) {
                SDL_CloseGamepad(gamepad_);
                gamepad_ = nullptr;
                insert("controllerConnected", false);
                insert("controllerIndex", -1);
                insert("controllerIdentity", QString());
            } else if (event.type == SDL_EVENT_GAMEPAD_BUTTON_DOWN) {
                const bool allowed = dispatchAllowed();
                qInfo() << "SDL button event received"
                        << "button=" << event.gbutton.button
                        << "focused_window=" << focusedWindow_
                        << "lulu_xid=" << (window_ ? window_->winId() : 0)
                        << "luluPresented=" << luluPresented_
                        << "dispatch=" << (allowed ? "yes" : "no");
                if (!allowed)
                    continue;
                static const std::pair<SDL_GamepadButton, const char *> routes[] = {
                    {SDL_GAMEPAD_BUTTON_DPAD_UP, "up"}, {SDL_GAMEPAD_BUTTON_DPAD_DOWN, "down"},
                    {SDL_GAMEPAD_BUTTON_DPAD_LEFT, "left"}, {SDL_GAMEPAD_BUTTON_DPAD_RIGHT, "right"},
                    {SDL_GAMEPAD_BUTTON_SOUTH, "confirm"}, {SDL_GAMEPAD_BUTTON_EAST, "back"},
                    {SDL_GAMEPAD_BUTTON_WEST, "options"},
                    {SDL_GAMEPAD_BUTTON_LEFT_SHOULDER, "leftShoulder"},
                    {SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER, "rightShoulder"},
                };
                for (const auto &[button, action] : routes) {
                    if (event.gbutton.button == button) {
                        publish(action);
                        break;
                    }
                }
            }
        }
    }

private:
    void publish(const char *action)
    {
        qInfo() << "SDL semantic navigation dispatch" << action;
        insert("action", QString::fromLatin1(action));
        insert("actionSerial", value("actionSerial").toInt() + 1);
        if (guideProcess_)
            return;
        static const std::pair<const char *, const char *> routes[] = {
            {"up", "controllerUp"}, {"down", "controllerDown"},
            {"left", "controllerLeft"}, {"right", "controllerRight"},
            {"confirm", "activate"}, {"back", "back"},
            {"options", "openSelectedGameOptions"},
            {"leftShoulder", "controllerShoulder"},
            {"rightShoulder", "controllerShoulder"},
        };
        for (const auto &[name, function] : routes) {
            if (qstrcmp(name, action) == 0) {
                if (qstrcmp(function, "controllerShoulder") == 0) {
                    const int delta = qstrcmp(action, "leftShoulder") == 0 ? -1 : 1;
                    QMetaObject::invokeMethod(window_, function, Q_ARG(QVariant, delta));
                } else {
                    QMetaObject::invokeMethod(window_, function);
                }
                break;
            }
        }
    }
    bool dispatchAllowed() const
    {
        return window_ && (luluPresented_ || guideProcess_);
    }

    void setupPresentationObserver()
    {
        presentationConnection_ = xcb_connect(nullptr, nullptr);
        if (!presentationConnection_ || xcb_connection_has_error(presentationConnection_)) {
            qWarning() << "Gamescope focus observer connection failed";
            if (presentationConnection_)
                xcb_disconnect(presentationConnection_);
            presentationConnection_ = nullptr;
            return;
        }

        const xcb_setup_t *setup = xcb_get_setup(presentationConnection_);
        const xcb_screen_t *screen = xcb_setup_roots_iterator(setup).data;
        if (!screen) {
            qWarning() << "Gamescope focus observer has no X11 screen";
            xcb_disconnect(presentationConnection_);
            presentationConnection_ = nullptr;
            return;
        }
        presentationRoot_ = screen->root;

        const xcb_intern_atom_cookie_t cookie =
            xcb_intern_atom(presentationConnection_, 0, sizeof("GAMESCOPE_FOCUSED_WINDOW") - 1,
                            "GAMESCOPE_FOCUSED_WINDOW");
        xcb_intern_atom_reply_t *reply = xcb_intern_atom_reply(presentationConnection_, cookie, nullptr);
        if (!reply) {
            qWarning() << "Gamescope focus observer could not intern atom";
            xcb_disconnect(presentationConnection_);
            presentationConnection_ = nullptr;
            return;
        }
        presentationAtom_ = reply->atom;
        free(reply);

        const uint32_t mask = XCB_EVENT_MASK_PROPERTY_CHANGE;
        xcb_change_window_attributes(presentationConnection_, presentationRoot_,
                                     XCB_CW_EVENT_MASK, &mask);
        xcb_flush(presentationConnection_);

        presentationNotifier_ = new QSocketNotifier(
            xcb_get_file_descriptor(presentationConnection_), QSocketNotifier::Read, this);
        connect(presentationNotifier_, &QSocketNotifier::activated, this,
                &ControllerBridge::drainPresentationEvents);
        qInfo() << "Gamescope focus observer initialized"
                << "root=" << presentationRoot_
                << "atom=" << presentationAtom_
                << "fd=" << xcb_get_file_descriptor(presentationConnection_);
        updatePresentationState();
    }

    void drainPresentationEvents()
    {
        int processed = 0;
        while (processed++ < 32) {
            xcb_generic_event_t *event = xcb_poll_for_event(presentationConnection_);
            if (!event)
                break;
            const uint8_t responseType = event->response_type & ~0x80;
            if (responseType == XCB_PROPERTY_NOTIFY) {
                const auto *property = reinterpret_cast<const xcb_property_notify_event_t *>(event);
                if (property->window == presentationRoot_ && property->atom == presentationAtom_) {
                    updatePresentationState();
                }
            }
            free(event);
        }
    }

    void updatePresentationState()
    {
        bool presented = false;
        uint32_t focusedWindow = 0;
        if (presentationConnection_ && presentationAtom_ && window_) {
            const auto cookie = xcb_get_property(
                presentationConnection_, 0, presentationRoot_, presentationAtom_,
                XCB_GET_PROPERTY_TYPE_ANY, 0, 1);
            xcb_get_property_reply_t *reply = xcb_get_property_reply(presentationConnection_, cookie, nullptr);
            if (reply) {
                if (reply->format == 32 && xcb_get_property_value_length(reply) >= static_cast<int>(sizeof(uint32_t))) {
                    const auto *value = static_cast<const uint32_t *>(xcb_get_property_value(reply));
                    focusedWindow = *value;
                    presented = focusedWindow == window_->winId();
                }
                free(reply);
            }
        }
        const bool changed = focusedWindow != focusedWindow_ || presented != luluPresented_;
        focusedWindow_ = focusedWindow;
        if (changed) {
            qInfo() << "Gamescope focus state"
                    << "focused_window=" << focusedWindow_
                    << "lulu_xid=" << (window_ ? window_->winId() : 0)
                    << "luluPresented=" << presented;
            luluPresented_ = presented;
            insert("luluPresented", presented);
        }
    }

    uint32_t windowProperty(xcb_window_t window, const char *name)
    {
        const auto cookie = xcb_intern_atom(presentationConnection_, 0, std::strlen(name), name);
        auto *atom = xcb_intern_atom_reply(presentationConnection_, cookie, nullptr);
        if (!atom)
            return 0;
        const auto property = xcb_get_property(presentationConnection_, 0, window, atom->atom,
                                               XCB_GET_PROPERTY_TYPE_ANY, 0, 1);
        auto *reply = xcb_get_property_reply(presentationConnection_, property, nullptr);
        uint32_t value = 0;
        if (reply && reply->format == 32
            && xcb_get_property_value_length(reply) >= static_cast<int>(sizeof(uint32_t)))
            value = *static_cast<const uint32_t *>(xcb_get_property_value(reply));
        free(reply);
        free(atom);
        return value;
    }

    QQuickWindow *window_;
    QTimer timer_;
    static constexpr const char *dbusInterface = "org.shadowblip.Input.DBusDevice";
    xcb_connection_t *presentationConnection_ = nullptr;
    xcb_window_t presentationRoot_ = XCB_WINDOW_NONE;
    xcb_atom_t presentationAtom_ = XCB_ATOM_NONE;
    QSocketNotifier *presentationNotifier_ = nullptr;
    bool luluPresented_ = false;
    uint32_t focusedWindow_ = 0;
    xcb_window_t targetWindow_ = XCB_WINDOW_NONE;
    uint32_t targetPid_ = 0;
    QProcess *guideProcess_ = nullptr;
    QTimer dbusDiscoveryTimer_;
    QHash<QString, DbusInputRelay *> dbusRelays_;
    QString guideOwnerComposite_;
    SDL_Gamepad *gamepad_ = nullptr;
    int renderTimelineFrames_ = 0;
    qint64 renderFrameStartNs_ = 0;
};

void DbusInputRelay::onInputEvent(const QString &event, double value)
{
    owner_->onDbusInputEvent(compositePath_, event, value);
}

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
    qInstallMessageHandler(diagnosticMessageHandler);
    QGuiApplication application(argc, argv);
    QQmlApplicationEngine engine;
    ControllerBridge controller(nullptr, &application);
    CatalogueModel catalogueModel(&application);
    RecentModel recentModel(&catalogueModel, &application);
    engine.rootContext()->setContextProperty("controllerBridge", &controller);
    // The native catalogue model is authoritative for the migrated Recent
    // consumer; Library and Store remain on their existing snapshot paths.
    engine.rootContext()->setContextProperty("catalogueModel", &catalogueModel);
    engine.rootContext()->setContextProperty("recentModel", &recentModel);
    const QString qmlPath = qEnvironmentVariable("LULU_UI_FILE", "/opt/lulu/ui/ConsoleShell.qml");
    engine.load(QUrl::fromLocalFile(qmlPath));

    if (engine.rootObjects().isEmpty())
        return EXIT_FAILURE;

    auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
    if (!window)
        return EXIT_FAILURE;

    window->create();
    controller.setWindow(window);
    if (!setSteamGame(window))
        return EXIT_FAILURE;

    window->show();
    return application.exec();
}

#include "lulu-shell.moc"
