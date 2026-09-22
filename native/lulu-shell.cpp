#include <QGuiApplication>
#include <QDebug>
#include <QFile>
#include <QDir>
#include <QDBusConnection>
#include <QDBusInterface>
#include <QDBusMessage>
#include <QDBusVariant>
#include <QDBusArgument>
#include <QDBusObjectPath>
#include <QDBusServiceWatcher>
#include <QDBusConnectionInterface>
#include <QDBusPendingCallWatcher>
#include <QProcess>
#include <QQmlContext>
#include <QQmlPropertyMap>
#include <QQmlApplicationEngine>
#include <QQuickWindow>
#include <QQuickRenderTarget>
#include <QSocketNotifier>
#include <QTimer>
#include <qnativeinterface.h>
#include <QUrl>
#include <QSettings>
#include <QUuid>
#include <QVariantList>
#include <QHash>
#include <QSet>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <algorithm>
#include <QtWebEngineQuick/QtWebEngineQuick>

#include <SDL3/SDL.h>
#include <xcb/xcb.h>
#include <xcb/xcb_keysyms.h>
#include <X11/keysym.h>

#include <cstdlib>
#include <csignal>
#include <cstring>
#include <string>
#include <unistd.h>
#include "catalogue-model.h"
#include "recent-model.h"
#include "mudos-glass-item.h"

namespace {

class StoreBookmarkBridge final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QVariantList bookmarks READ bookmarks NOTIFY bookmarksChanged)
public:
    explicit StoreBookmarkBridge(QObject *parent = nullptr) : QObject(parent) { reload(); }

    QVariantList bookmarks() const { return bookmarks_; }

    Q_INVOKABLE bool addBookmark(const QString &rawUrl)
    {
        QString value = rawUrl.trimmed();
        if (value.isEmpty()) return false;
        if (!value.contains(QStringLiteral("://"))) value.prepend(QStringLiteral("https://"));
        const QUrl url(value);
        if (!url.isValid() || (url.scheme() != QStringLiteral("http") && url.scheme() != QStringLiteral("https"))
            || url.host().isEmpty()) return false;
        for (const QVariant &item : bookmarks_)
            if (item.toMap().value(QStringLiteral("url")).toString() == url.toString()) return true;
        QVariantMap item;
        item.insert(QStringLiteral("id"), QUuid::createUuid().toString(QUuid::WithoutBraces));
        item.insert(QStringLiteral("url"), url.toString());
        item.insert(QStringLiteral("display_name"), url.host());
        bookmarks_.append(item);
        save();
        emit bookmarksChanged();
        return true;
    }

    Q_INVOKABLE void removeBookmark(const QString &id)
    {
        for (int i = bookmarks_.size() - 1; i >= 0; --i)
            if (bookmarks_[i].toMap().value(QStringLiteral("id")).toString() == id) bookmarks_.removeAt(i);
        save();
        emit bookmarksChanged();
    }

    Q_INVOKABLE bool updateBookmarkName(const QString &id, const QString &rawName)
    {
        const QString name = rawName.trimmed();
        if (name.isEmpty() || name.size() > 128) return false;
        for (QVariant &item : bookmarks_) {
            QVariantMap value = item.toMap();
            if (value.value(QStringLiteral("id")).toString() == id) {
                value.insert(QStringLiteral("display_name"), name);
                item = value;
                save();
                emit bookmarksChanged();
                return true;
            }
        }
        return false;
    }

    Q_INVOKABLE bool updateBookmarkUrl(const QString &id, const QString &rawUrl)
    {
        QString value = rawUrl.trimmed();
        if (value.isEmpty()) return false;
        if (!value.contains(QStringLiteral("://"))) value.prepend(QStringLiteral("https://"));
        const QUrl url(value);
        if (!url.isValid() || (url.scheme() != QStringLiteral("http") && url.scheme() != QStringLiteral("https"))
            || url.host().isEmpty()) return false;
        for (const QVariant &item : bookmarks_)
            if (item.toMap().value(QStringLiteral("id")).toString() != id
                && item.toMap().value(QStringLiteral("url")).toString() == url.toString()) return false;
        for (QVariant &item : bookmarks_) {
            QVariantMap bookmark = item.toMap();
            if (bookmark.value(QStringLiteral("id")).toString() == id) {
                bookmark.insert(QStringLiteral("url"), url.toString());
                item = bookmark;
                save();
                emit bookmarksChanged();
                return true;
            }
        }
        return false;
    }

signals:
    void bookmarksChanged();

private:
    void reload()
    {
        QSettings settings(QSettings::IniFormat, QSettings::UserScope, QStringLiteral("Mudos"), QStringLiteral("lulu"));
        const auto value = settings.value(QStringLiteral("stores/bookmarks")).toJsonArray();
        for (const auto &entry : value) bookmarks_.append(entry.toObject().toVariantMap());
    }
    void save()
    {
        QJsonArray array;
        for (const QVariant &entry : bookmarks_) array.append(QJsonObject::fromVariantMap(entry.toMap()));
        QSettings settings(QSettings::IniFormat, QSettings::UserScope, QStringLiteral("Mudos"), QStringLiteral("lulu"));
        settings.setValue(QStringLiteral("stores/bookmarks"), array);
        settings.sync();
    }
    QVariantList bookmarks_;
};

class PluginStoreCardBridge final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QVariantList cards READ cards NOTIFY cardsChanged)
public:
    explicit PluginStoreCardBridge(QObject *parent = nullptr) : QObject(parent) { reload(); }

    QVariantList cards() const { return cards_; }

signals:
    void cardsChanged();

private:
    void reload()
    {
        QVariantList next;
        const QString root = QString::fromUtf8(qgetenv("LULU_INSTALL_ROOT"));
        const QDir plugins(root.isEmpty() ? QDir::currentPath() + QStringLiteral("/config/plugins")
                                          : root + QStringLiteral("/config/plugins"));
        const QStringList pluginDirs = plugins.entryList(QDir::Dirs | QDir::NoDotAndDotDot, QDir::Name);
        for (const QString &pluginDir : pluginDirs) {
            QFile file(plugins.filePath(pluginDir + QStringLiteral("/store-card.json")));
            if (!file.open(QIODevice::ReadOnly)) continue;
            const QJsonDocument document = QJsonDocument::fromJson(file.readAll());
            if (!document.isObject()) continue;
            const QJsonObject object = document.object();
            if (object.value(QStringLiteral("id")).toString().isEmpty()
                || object.value(QStringLiteral("label")).toString().isEmpty()
                || object.value(QStringLiteral("url")).toString().isEmpty()) continue;
            QVariantMap card;
            for (auto it = object.begin(); it != object.end(); ++it)
                card.insert(it.key(), it.value().toVariant());
            card.insert(QStringLiteral("kind"), QStringLiteral("store"));
            card.insert(QStringLiteral("removable"), false);
            next.append(card);
        }
        if (next != cards_) { cards_ = next; emit cardsChanged(); }
    }

    QVariantList cards_;
};

class SystemStatusBridge final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool networkConnected READ networkConnected NOTIFY networkConnectedChanged)
    Q_PROPERTY(QString networkConnectionType READ networkConnectionType NOTIFY networkConnectionTypeChanged)
    Q_PROPERTY(QString bluetoothState READ bluetoothState NOTIFY bluetoothStateChanged)
    Q_PROPERTY(bool bluetoothPowered READ bluetoothPowered NOTIFY bluetoothStateChanged)
    Q_PROPERTY(uint activeDownloadCount READ activeDownloadCount NOTIFY activeDownloadCountChanged)
    Q_PROPERTY(QString acquisitionSnapshot READ acquisitionSnapshot NOTIFY acquisitionSnapshotChanged)
    Q_PROPERTY(bool acquisitionAvailable READ acquisitionAvailable NOTIFY acquisitionAvailabilityChanged)

public:
    explicit SystemStatusBridge(QObject *parent = nullptr)
        : QObject(parent), bluezWatcher_(new QDBusServiceWatcher(
              QStringLiteral("org.bluez"), QDBusConnection::systemBus(),
              QDBusServiceWatcher::WatchForRegistration
                   | QDBusServiceWatcher::WatchForUnregistration, this))
          , acquisitionWatcher_(new QDBusServiceWatcher(
              QStringLiteral("org.lulu.Acquisitiond"), QDBusConnection::sessionBus(),
              QDBusServiceWatcher::WatchForRegistration
                  | QDBusServiceWatcher::WatchForUnregistration, this))
    {
        QDBusConnection bus = QDBusConnection::systemBus();
        bus.connect(QStringLiteral("org.freedesktop.NetworkManager"),
                    QStringLiteral("/org/freedesktop/NetworkManager"),
                    QStringLiteral("org.freedesktop.DBus.Properties"),
                    QStringLiteral("PropertiesChanged"), this,
                    SLOT(onNetworkPropertiesChanged(QString,QVariantMap,QStringList)));
        bus.connect(QStringLiteral("org.bluez"), QString(),
                    QStringLiteral("org.freedesktop.DBus.Properties"),
                    QStringLiteral("PropertiesChanged"), this,
                    SLOT(onBluezPropertiesChanged(QString,QVariantMap,QStringList)));
        bus.connect(QStringLiteral("org.bluez"), QStringLiteral("/"),
                    QStringLiteral("org.freedesktop.DBus.ObjectManager"),
                    QStringLiteral("InterfacesAdded"), this,
                    SLOT(onBluezInterfacesAdded(QDBusObjectPath,QVariantMap)));
        bus.connect(QStringLiteral("org.bluez"), QStringLiteral("/"),
                    QStringLiteral("org.freedesktop.DBus.ObjectManager"),
                    QStringLiteral("InterfacesRemoved"), this,
                    SLOT(onBluezInterfacesRemoved(QDBusObjectPath,QStringList)));
        connect(bluezWatcher_, &QDBusServiceWatcher::serviceRegistered,
                this, &SystemStatusBridge::refreshBluetooth);
        connect(bluezWatcher_, &QDBusServiceWatcher::serviceUnregistered,
                 this, &SystemStatusBridge::refreshBluetooth);
        connect(acquisitionWatcher_, &QDBusServiceWatcher::serviceRegistered,
                this, &SystemStatusBridge::onAcquisitionRegistered);
        connect(acquisitionWatcher_, &QDBusServiceWatcher::serviceUnregistered,
                this, &SystemStatusBridge::onAcquisitionUnregistered);
        QDBusConnection::sessionBus().connect(
            QStringLiteral("org.lulu.Acquisitiond"),
            QStringLiteral("/org/lulu/Acquisition"),
            QStringLiteral("org.lulu.Acquisition"),
            QStringLiteral("StateChanged"), this,
            SLOT(onAcquisitionStateChanged(QString)));
        refreshNetwork();
        refreshBluetooth();
        refreshAcquisitionStatus();
    }

    bool networkConnected() const { return networkConnected_; }
    QString bluetoothState() const { return bluetoothState_; }
    QString networkConnectionType() const { return networkConnectionType_; }
    bool bluetoothPowered() const { return bluetoothState_ == QStringLiteral("powered"); }
    uint activeDownloadCount() const { return activeDownloadCount_; }
    QString acquisitionSnapshot() const { return acquisitionSnapshot_; }
    bool acquisitionAvailable() const { return acquisitionAvailable_; }

signals:
    void networkConnectedChanged();
    void networkConnectionTypeChanged();
    void bluetoothStateChanged();
    void activeDownloadCountChanged();
    void acquisitionSnapshotChanged();
    void acquisitionAvailabilityChanged();

private slots:
    void onNetworkPropertiesChanged(const QString &interfaceName,
                                    const QVariantMap &changed,
                                    const QStringList &)
    {
        if (interfaceName == QStringLiteral("org.freedesktop.NetworkManager")
                && (changed.contains(QStringLiteral("State"))
                    || changed.contains(QStringLiteral("Connectivity"))))
            refreshNetwork();
    }

    void onBluezPropertiesChanged(const QString &interfaceName,
                                  const QVariantMap &,
                                  const QStringList &)
    {
        if (interfaceName == QStringLiteral("org.bluez.Adapter1"))
            refreshBluetooth();
    }

    void onBluezInterfacesAdded(const QDBusObjectPath &, const QVariantMap &interfaces)
    {
        if (interfaces.contains(QStringLiteral("org.bluez.Adapter1")))
            refreshBluetooth();
    }

    void onBluezInterfacesRemoved(const QDBusObjectPath &, const QStringList &interfaces)
    {
        if (interfaces.contains(QStringLiteral("org.bluez.Adapter1")))
            refreshBluetooth();
    }

    void onAcquisitionStateChanged(const QString &snapshot)
    {
        updateAcquisitionSnapshot(snapshot);
    }

    void onAcquisitionRegistered(const QString &)
    {
        refreshAcquisitionStatus();
    }

    void onAcquisitionUnregistered(const QString &)
    {
        updateAcquisitionSnapshot(QStringLiteral("{\"jobs\":[],\"activeDownloadCount\":0}"), false);
    }

private:
    void refreshAcquisitionStatus()
    {
        QDBusInterface acquisition(QStringLiteral("org.lulu.Acquisitiond"),
                                   QStringLiteral("/org/lulu/Acquisition"),
                                   QStringLiteral("org.lulu.Acquisition"),
                                   QDBusConnection::sessionBus());
        const QDBusMessage reply = acquisition.call(QStringLiteral("GetSnapshot"));
        if (reply.type() == QDBusMessage::ReplyMessage && !reply.arguments().isEmpty())
            updateAcquisitionSnapshot(reply.arguments().constFirst().toString(), true);
        else
            updateAcquisitionSnapshot(QStringLiteral("{\"jobs\":[],\"activeDownloadCount\":0}"), false);
    }

    void updateAcquisitionSnapshot(const QString &snapshot, bool available = true)
    {
        const QJsonDocument document = QJsonDocument::fromJson(snapshot.toUtf8());
        if (!document.isObject())
            return;
        const uint count = document.object().value(QStringLiteral("activeDownloadCount")).toInt(0);
        if (count != activeDownloadCount_) {
            activeDownloadCount_ = count;
            emit activeDownloadCountChanged();
        }
        if (snapshot != acquisitionSnapshot_) {
            acquisitionSnapshot_ = snapshot;
            emit acquisitionSnapshotChanged();
        }
        if (available != acquisitionAvailable_) {
            acquisitionAvailable_ = available;
            emit acquisitionAvailabilityChanged();
        }
    }

    static bool networkStateIsConnected(uint state)
    {
        // NetworkManager: CONNECTED_LOCAL/SITE/GLOBAL are all usable links.
        return state >= 50 && state <= 70;
    }

    void refreshNetwork()
    {
        QDBusInterface properties(QStringLiteral("org.freedesktop.NetworkManager"),
                                  QStringLiteral("/org/freedesktop/NetworkManager"),
                                  QStringLiteral("org.freedesktop.DBus.Properties"),
                                  QDBusConnection::systemBus());
        QDBusMessage reply = properties.call(QStringLiteral("Get"),
                                             QStringLiteral("org.freedesktop.NetworkManager"),
                                             QStringLiteral("State"));
        bool connected = false;
        QString connectionType;
        if (reply.type() == QDBusMessage::ReplyMessage && !reply.arguments().isEmpty()) {
            const QVariant value = reply.arguments().constFirst().value<QDBusVariant>().variant();
            connected = networkStateIsConnected(value.toUInt());
        }

        QDBusMessage activeReply = properties.call(
            QStringLiteral("Get"), QStringLiteral("org.freedesktop.NetworkManager"),
            QStringLiteral("ActiveConnections"));
        if (activeReply.type() == QDBusMessage::ReplyMessage
                && !activeReply.arguments().isEmpty()) {
            const QVariant value = activeReply.arguments().constFirst()
                .value<QDBusVariant>().variant();
            if (value.canConvert<QDBusArgument>()) {
                QDBusArgument argument = value.value<QDBusArgument>();
                argument.beginArray();
                while (!argument.atEnd()) {
                    QDBusObjectPath path;
                    argument >> path;
                    QDBusInterface activeConnection(
                        QStringLiteral("org.freedesktop.NetworkManager"), path.path(),
                        QStringLiteral("org.freedesktop.DBus.Properties"),
                        QDBusConnection::systemBus());
                    QDBusMessage defaultReply = activeConnection.call(
                        QStringLiteral("Get"),
                        QStringLiteral("org.freedesktop.NetworkManager.Connection.Active"),
                        QStringLiteral("Default"));
                    bool isDefault = defaultReply.type() == QDBusMessage::ReplyMessage
                        && !defaultReply.arguments().isEmpty()
                        && defaultReply.arguments().constFirst().value<QDBusVariant>()
                            .variant().toBool();
                    if (!isDefault)
                        continue;
                    QDBusMessage typeReply = activeConnection.call(
                        QStringLiteral("Get"),
                        QStringLiteral("org.freedesktop.NetworkManager.Connection.Active"),
                        QStringLiteral("Type"));
                    if (typeReply.type() == QDBusMessage::ReplyMessage
                            && !typeReply.arguments().isEmpty()) {
                        const QString type = typeReply.arguments().constFirst()
                            .value<QDBusVariant>().variant().toString();
                        if (type == QStringLiteral("802-3-ethernet"))
                            connectionType = QStringLiteral("ethernet");
                        else if (type == QStringLiteral("802-11-wireless"))
                            connectionType = QStringLiteral("wifi");
                    }
                    break;
                }
            }
        }
        if (connected != networkConnected_) {
            networkConnected_ = connected;
            emit networkConnectedChanged();
        }
        if (connectionType != networkConnectionType_) {
            networkConnectionType_ = connectionType;
            emit networkConnectionTypeChanged();
        }
    }

    void refreshBluetooth()
    {
        QString nextState = QStringLiteral("unavailable");
        QDBusConnectionInterface *busInterface = QDBusConnection::systemBus().interface();
        if (busInterface && busInterface->isServiceRegistered(QStringLiteral("org.bluez"))) {
            QDBusInterface manager(QStringLiteral("org.bluez"), QStringLiteral("/"),
                                   QStringLiteral("org.freedesktop.DBus.ObjectManager"),
                                   QDBusConnection::systemBus());
            const QDBusMessage reply = manager.call(QStringLiteral("GetManagedObjects"));
            QSet<QString> adapters;
            if (reply.type() == QDBusMessage::ReplyMessage && !reply.arguments().isEmpty()) {
                QMap<QDBusObjectPath, QMap<QString, QVariantMap>> objects;
                QDBusArgument argument = reply.arguments().constFirst().value<QDBusArgument>();
                argument >> objects;
                for (auto it = objects.cbegin(); it != objects.cend(); ++it) {
                    if (it.value().contains(QStringLiteral("org.bluez.Adapter1")))
                        adapters.insert(it.key().path());
                }
            }
            if (!adapters.isEmpty()) {
                nextState = QStringLiteral("off");
                for (const QString &path : adapters) {
                    QDBusInterface adapter(QStringLiteral("org.bluez"), path,
                                           QStringLiteral("org.freedesktop.DBus.Properties"),
                                           QDBusConnection::systemBus());
                    const QDBusMessage poweredReply = adapter.call(
                        QStringLiteral("Get"), QStringLiteral("org.bluez.Adapter1"),
                        QStringLiteral("Powered"));
                    if (poweredReply.type() == QDBusMessage::ReplyMessage
                            && !poweredReply.arguments().isEmpty()
                            && poweredReply.arguments().constFirst().value<QDBusVariant>()
                                   .variant().toBool()) {
                        nextState = QStringLiteral("powered");
                        break;
                    }
                }
            }
        }
        if (nextState != bluetoothState_) {
            bluetoothState_ = nextState;
            emit bluetoothStateChanged();
        }
    }

    bool networkConnected_ = false;
    QString networkConnectionType_;
    QString bluetoothState_ = QStringLiteral("unavailable");
    uint activeDownloadCount_ = 0;
    QString acquisitionSnapshot_ = QStringLiteral("{\"jobs\":[],\"activeDownloadCount\":0}");
    bool acquisitionAvailable_ = false;
    QDBusServiceWatcher *bluezWatcher_;
    QDBusServiceWatcher *acquisitionWatcher_;
};

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
        insert("textEntryShortcutSerial", 0);
        insert("luluPresented", false);
        insert("requestedSurface", QString());
        insert("guideSelection", 0);
        insert("controllers", QVariantList());
        insert("launchOverlayEnabled",
               qEnvironmentVariable("LULU_LAUNCH_OVERLAY_ENABLED", "true")
                   .compare(QStringLiteral("false"), Qt::CaseInsensitive) != 0);
        refreshDbusSubscriptions();
        QDBusConnection::sessionBus().connect(
            QStringLiteral("org.lulu.ConsoleSessiond"),
            QStringLiteral("/org/lulu/ConsoleSession"),
            QStringLiteral("org.lulu.ConsoleSession"),
            QStringLiteral("StateChanged"), this,
            SLOT(onSessionStateChanged(QString)));
        refreshSessionStatus();
        dbusDiscoveryTimer_.setInterval(500);
        connect(&dbusDiscoveryTimer_, &QTimer::timeout,
                this, &ControllerBridge::refreshDbusSubscriptions);
        dbusDiscoveryTimer_.start();
        keyboardOwnershipTimer_.setInterval(250);
        connect(&keyboardOwnershipTimer_, &QTimer::timeout,
                this, &ControllerBridge::refreshKeyboardOwnership);
        keyboardOwnershipTimer_.start();
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
        closeGamepads();
        SDL_QuitSubSystem(SDL_INIT_GAMEPAD);
    }

    void setWindow(QQuickWindow *window)
    {
        window_ = window;
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
    void onSessionStateChanged(const QString &stateJson)
    {
        updateControllersFromSessionState(stateJson);
        selectNavigationGamepad();
    }

    void onDbusInputEvent(const QString &compositePath, const QString &event, double value)
    {
        handleInputEvent(compositePath, event, value);
    }

private:
    void refreshSessionStatus()
    {
        QDBusInterface session(QStringLiteral("org.lulu.ConsoleSessiond"),
                               QStringLiteral("/org/lulu/ConsoleSession"),
                               QStringLiteral("org.lulu.ConsoleSession"),
                               QDBusConnection::sessionBus());
        const QDBusMessage reply = session.call(QStringLiteral("GetState"));
        if (reply.type() == QDBusMessage::ReplyMessage && !reply.arguments().isEmpty())
            updateControllersFromSessionState(reply.arguments().constFirst().toString());
    }

    void updateControllersFromSessionState(const QString &stateJson)
    {
        const QJsonDocument document = QJsonDocument::fromJson(stateJson.toUtf8());
        if (!document.isObject())
            return;
        insert(QStringLiteral("requestedSurface"),
               document.object().value(QStringLiteral("requested_surface")).toString());
        const QJsonObject controllerRoot = document.object().value(QStringLiteral("controller"))
            .toObject().value(QStringLiteral("controllers")).toObject();
        const QString navigationId = document.object().value(QStringLiteral("controller"))
            .toObject().value(QStringLiteral("navigation_controller_id")).toString();
        const QString navigationMode = document.object().value(QStringLiteral("controller"))
            .toObject().value(QStringLiteral("navigation_mode"))
            .toString(QStringLiteral("all"));
        navigationAll_ = navigationMode == QStringLiteral("all");
        QVariantList controllers;
        for (auto iterator = controllerRoot.constBegin(); iterator != controllerRoot.constEnd(); ++iterator) {
            const QJsonObject value = iterator.value().toObject();
            if (!value.value(QStringLiteral("connected")).toBool())
                continue;
            const int player = value.value(QStringLiteral("player")).toInt(0);
            if (player <= 0)
                continue;
            const QJsonObject battery = value.value(QStringLiteral("battery")).toObject();
            const QString batteryKind = battery.value(QStringLiteral("kind"))
                .toString(QStringLiteral("unknown"));
            const QJsonValue percentage = battery.value(QStringLiteral("percentage"));
            QVariantMap controller;
            controller.insert(QStringLiteral("index"), player);
            controller.insert(QStringLiteral("connected"), true);
            controller.insert(QStringLiteral("identity"),
                              value.value(QStringLiteral("physical_identity")).toString());
            controller.insert(QStringLiteral("batteryKind"), batteryKind);
            controller.insert(QStringLiteral("batteryPercentage"),
                              percentage.isDouble() ? percentage.toInt() : -1);
            controller.insert(QStringLiteral("battery"),
                              batteryKind == QStringLiteral("percent") && percentage.isDouble()
                                  ? QString::number(percentage.toInt()) + QStringLiteral("%")
                                  : QStringLiteral("Unknown"));
            controllers.append(controller);
            if (iterator.key() == navigationId)
                navigationPlayer_ = player;
        }
        std::sort(controllers.begin(), controllers.end(), [](const QVariant &left, const QVariant &right) {
            return left.toMap().value(QStringLiteral("index")).toInt()
                < right.toMap().value(QStringLiteral("index")).toInt();
        });
        insert(QStringLiteral("controllers"), controllers);
        selectNavigationGamepad();
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
        releaseGuideKeyboard();
        if (!guideOwnerComposite_.isEmpty())
            setInterceptMode(guideOwnerComposite_, 1);
        guideOwnerComposite_.clear();
        clearTarget();
    }

    void captureGuideKeyboard()
    {
        if (!presentationConnection_ || globalGuideRoot_ == XCB_WINDOW_NONE)
            return;
        const auto keySymbols = xcb_key_symbols_alloc(presentationConnection_);
        if (!keySymbols)
            return;
        const struct KeyAction { xcb_keysym_t symbol; const char *action; } keys[] = {
            {XK_Up, "ui_up"}, {XK_Down, "ui_down"},
            {XK_Left, "ui_left"}, {XK_Right, "ui_right"},
            {XK_Return, "ui_accept"}, {XK_KP_Enter, "ui_accept"},
            {XK_Escape, "ui_back"}, {XK_BackSpace, "ui_back"},
        };
        for (const auto &key : keys) {
            const auto keycodes = xcb_key_symbols_get_keycode(keySymbols, key.symbol);
            if (!keycodes || keycodes[0] == XCB_NO_SYMBOL) {
                free(keycodes);
                continue;
            }
            const auto keycode = keycodes[0];
            const auto cookie = xcb_grab_key_checked(
                presentationConnection_, 1, globalGuideRoot_, XCB_MOD_MASK_ANY,
                keycode, XCB_GRAB_MODE_ASYNC, XCB_GRAB_MODE_ASYNC);
            if (auto *error = xcb_request_check(presentationConnection_, cookie)) {
                qWarning() << "Guide global key grab failed" << key.action << error->error_code;
                free(error);
            } else {
                guideKeyboardActions_.insert(keycode, QString::fromLatin1(key.action));
            }
            free(keycodes);
        }
        xcb_key_symbols_free(keySymbols);
        xcb_flush(presentationConnection_);
    }

    void releaseGuideKeyboard()
    {
        if (!presentationConnection_ || globalGuideRoot_ == XCB_WINDOW_NONE)
            return;
        for (auto iterator = guideKeyboardActions_.cbegin();
             iterator != guideKeyboardActions_.cend(); ++iterator)
            xcb_ungrab_key(presentationConnection_, iterator.key(), globalGuideRoot_, XCB_MOD_MASK_ANY);
        guideKeyboardActions_.clear();
        xcb_flush(presentationConnection_);
    }

    void sendGuideKeyboardAction(const QString &action)
    {
        if (!guideProcess_)
            return;
        guideProcess_->write(action.toUtf8() + " edge=down\n");
        guideProcess_->write(action.toUtf8() + " edge=up\n");
    }

    void handleInputEvent(const QString &compositePath, const QString &event, double value)
    {
        // A request in flight is already an exclusive ownership transition.
        // Discard the event; never let it cross into the next owner.
        if (oskRequestPending_)
            return;
        // OSK mode owns the intercepted D-Bus stream. The bridge consumes it
        // and feeds the private gamepad-osk device; Guide must not also act.
        if (oskActive_)
            return;
        if (event == QStringLiteral("ui_context") && pendingGuide_
            && compositePath == guideOwnerComposite_) {
            if (value == 1.0) {
                if (!guideChordConsumed_) {
                    guideChordConsumed_ = true;
                    showKeyboard();
                }
                return;
            }
            if (value == 0.0)
                return;
        }
        if (event == QStringLiteral("ui_guide")) {
            if (value == 1.0) {
                if (guideProcess_ && compositePath == guideOwnerComposite_) {
                    guideProcess_->write("ui_guide edge=down\n");
                    return;
                }
                if (!pendingGuide_) {
                    pendingGuide_ = true;
                    guideChordConsumed_ = false;
                    guideOwnerComposite_ = compositePath;
                }
                return;
            }
            if (value == 0.0 && pendingGuide_ && compositePath == guideOwnerComposite_) {
                const bool chordConsumed = guideChordConsumed_;
                pendingGuide_ = false;
                guideChordConsumed_ = false;
                if (!chordConsumed) {
                    startGuide();
                } else {
                    guideOwnerComposite_.clear();
                }
                return;
            }
            if (!(guideProcess_ && compositePath == guideOwnerComposite_))
                return;
        }
        if (value != 1.0 && value != 0.0)
            return;
        if (guideProcess_ && compositePath == guideOwnerComposite_
            && (event == QStringLiteral("ui_guide")
                              || event == QStringLiteral("ui_up")
                              || event == QStringLiteral("ui_down")
                              || event == QStringLiteral("ui_accept")
                              || event == QStringLiteral("ui_back"))) {
            const char *edge = value == 1.0 ? "down" : "up";
            guideProcess_->write(event.toUtf8() + " edge=" + edge + '\n');
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
        if (guideProcess_)
            return true;
        if (!presentationConnection_ || !focusedWindow_ || !window_) {
            restoreInput();
            return false;
        }
        targetWindow_ = focusedWindow_;
        targetPid_ = windowProperty(targetWindow_, "_NET_WM_PID");
        guideProcess_ = new QProcess(this);
        connect(guideProcess_, &QProcess::finished, this,
                [this](int, QProcess::ExitStatus) { finishGuide(); });
        const QString guideExecutable = qEnvironmentVariable(
            "LULU_GUIDE_EXECUTABLE", "/opt/lulu/bin/mudos-guide");
        guideProcess_->start(guideExecutable, {
            QString::number(targetWindow_), QString::number(targetPid_)
        });
        if (!guideProcess_->waitForStarted(1000)) {
            finishGuide();
            return false;
        }
        captureGuideKeyboard();
        return true;
    }

    void showKeyboard()
    {
        if (oskActive_ || oskRequestPending_)
            return;
        pendingGuide_ = false;
        guideChordConsumed_ = false;
        guideOwnerComposite_.clear();
        insert("textEntryShortcutSerial",
               value(QStringLiteral("textEntryShortcutSerial")).toInt() + 1);
        oskRequestPending_ = true;
        QDBusInterface consoled(QStringLiteral("org.lulu.Consoled"),
                                 QStringLiteral("/org/lulu/Console"),
                                 QStringLiteral("org.lulu.Console"),
                                 QDBusConnection::sessionBus());
        auto *watcher = new QDBusPendingCallWatcher(
            consoled.asyncCall(QStringLiteral("ShowKeyboard")), this);
        connect(watcher, &QDBusPendingCallWatcher::finished, this,
                [this](QDBusPendingCallWatcher *finished) {
                    const QDBusMessage reply = finished->reply();
                    oskRequestPending_ = false;
                    if (reply.type() == QDBusMessage::ErrorMessage) {
                        qWarning() << "Guide chord OSK show failed" << reply.errorMessage();
                        oskActive_ = false;
                    } else {
                        oskActive_ = !reply.arguments().isEmpty()
                            && reply.arguments().constFirst().toBool();
                        rearmRequired_ = oskActive_;
                    }
                    finished->deleteLater();
                });
    }

    void refreshKeyboardOwnership()
    {
        QDBusInterface consoled(QStringLiteral("org.lulu.Consoled"),
                                QStringLiteral("/org/lulu/Console"),
                                QStringLiteral("org.lulu.Console"),
                                QDBusConnection::sessionBus());
        if (oskRequestPending_)
            return;
        auto *watcher = new QDBusPendingCallWatcher(
            consoled.asyncCall(QStringLiteral("KeyboardVisible")), this);
        connect(watcher, &QDBusPendingCallWatcher::finished, this,
                [this](QDBusPendingCallWatcher *finished) {
                    const QDBusMessage reply = finished->reply();
                    if (reply.type() == QDBusMessage::ReplyMessage
                        && !reply.arguments().isEmpty())
                    {
                        const bool wasActive = oskActive_;
                        oskActive_ = reply.arguments().constFirst().toBool();
                        if (wasActive && !oskActive_)
                            rearmRequired_ = true;
                    }
                    finished->deleteLater();
                });
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
            if (guideProcess_)
                guideProcess_->write("reset_edges\n");
            iterator.value()->deleteLater();
            iterator = dbusRelays_.erase(iterator);
        }
    }


    void scanGamepads()
    {
        closeGamepads();
        int count = 0;
        SDL_JoystickID *ids = SDL_GetGamepads(&count);
        qInfo() << "SDL gamepad scan count=" << count;
        if (ids && count > 0) {
            const int requested = std::max(0, std::min(navigationPlayer_ - 1, count - 1));
            gamepadSlot_ = requested;
            if (navigationAll_) {
                for (int index = 0; index < count; ++index) {
                    if (auto *gamepad = SDL_OpenGamepad(ids[index])) {
                        allGamepads_.insert(ids[index], gamepad);
                        if (!gamepad_)
                            gamepad_ = gamepad;
                        qInfo() << "SDL all-navigation gamepad opened"
                                << SDL_GetGamepadName(gamepad);
                    }
                }
            } else {
                gamepad_ = SDL_OpenGamepad(ids[requested]);
            }
            if (gamepad_) {
                qInfo() << "SDL gamepad opened" << SDL_GetGamepadName(gamepad_);
                insert("controllerConnected", true);
                insert("controllerIndex", 1);
                insert("controllerIdentity", QString::fromUtf8(SDL_GetGamepadName(gamepad_)));
            }
        }
        SDL_free(ids);
    }

    void selectNavigationGamepad()
    {
        if (navigationAll_) {
            if (allGamepads_.isEmpty())
                scanGamepads();
            return;
        }
        if (!gamepad_)
            return;
        const int requested = std::max(0, navigationPlayer_ - 1);
        if (requested == gamepadSlot_)
            return;
        SDL_CloseGamepad(gamepad_);
        gamepad_ = nullptr;
        scanGamepads();
    }

    void poll()
    {
        if (rearmRequired_ && !oskActive_ && !oskRequestPending_
            && controllerButtonsReleased())
            rearmRequired_ = false;
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_GAMEPAD_ADDED && navigationAll_) {
                if (auto *gamepad = SDL_OpenGamepad(event.gdevice.which)) {
                    allGamepads_.insert(event.gdevice.which, gamepad);
                    if (!gamepad_)
                        gamepad_ = gamepad;
                    insert("controllerConnected", true);
                }
            } else if (event.type == SDL_EVENT_GAMEPAD_ADDED && !gamepad_) {
                gamepad_ = SDL_OpenGamepad(event.gdevice.which);
                if (gamepad_) {
                    insert("controllerConnected", true);
                    insert("controllerIndex", 1);
                    insert("controllerIdentity", QString::fromUtf8(SDL_GetGamepadName(gamepad_)));
                }
            } else if (event.type == SDL_EVENT_GAMEPAD_REMOVED && navigationAll_) {
                auto iterator = allGamepads_.find(event.gdevice.which);
                if (iterator != allGamepads_.end()) {
                    if (iterator.value() == gamepad_)
                        gamepad_ = nullptr;
                    SDL_CloseGamepad(iterator.value());
                    allGamepads_.erase(iterator);
                }
                if (!gamepad_ && !allGamepads_.isEmpty())
                    gamepad_ = allGamepads_.constBegin().value();
                if (allGamepads_.isEmpty()) {
                    insert("controllerConnected", false);
                    insert("controllerIndex", -1);
                    insert("controllerIdentity", QString());
                }
            } else if (event.type == SDL_EVENT_GAMEPAD_REMOVED && gamepad_
                       && event.gdevice.which == SDL_GetGamepadID(gamepad_)) {
                SDL_CloseGamepad(gamepad_);
                gamepad_ = nullptr;
                insert("controllerConnected", false);
                insert("controllerIndex", -1);
                insert("controllerIdentity", QString());
                // The remaining SDL device does not emit an add event when
                // the selected device disappears; reopen the current
                // navigation slot immediately for failover.
                scanGamepads();
            } else if (event.type == SDL_EVENT_GAMEPAD_BUTTON_DOWN) {
                if (!navigationAll_ && (!gamepad_
                    || event.gbutton.which != SDL_GetGamepadID(gamepad_)))
                    continue;
                if (rearmRequired_)
                    continue;
                const bool allowed = dispatchAllowed();
                if (!allowed)
                    continue;
                static const std::pair<SDL_GamepadButton, const char *> routes[] = {
                    {SDL_GAMEPAD_BUTTON_DPAD_UP, "up"}, {SDL_GAMEPAD_BUTTON_DPAD_DOWN, "down"},
                    {SDL_GAMEPAD_BUTTON_DPAD_LEFT, "left"}, {SDL_GAMEPAD_BUTTON_DPAD_RIGHT, "right"},
                    {SDL_GAMEPAD_BUTTON_SOUTH, "confirm"}, {SDL_GAMEPAD_BUTTON_EAST, "back"},
                    {SDL_GAMEPAD_BUTTON_WEST, "options"},
                    {SDL_GAMEPAD_BUTTON_NORTH, "downloads"},
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
        insert("action", QString::fromLatin1(action));
        insert("actionSerial", value("actionSerial").toInt() + 1);
        if (guideProcess_)
            return;
        static const std::pair<const char *, const char *> routes[] = {
            {"up", "controllerUp"}, {"down", "controllerDown"},
            {"left", "controllerLeft"}, {"right", "controllerRight"},
            {"confirm", "activate"}, {"back", "back"},
            {"options", "openSelectedGameOptions"}, {"downloads", "openDownloadsGlobal"},
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
        return window_ && !oskActive_ && !oskRequestPending_ && !rearmRequired_
            && (luluPresented_ || guideProcess_);
    }

    bool controllerButtonsReleased() const
    {
        if (navigationAll_) {
            for (auto *gamepad : allGamepads_)
                for (const auto button : {SDL_GAMEPAD_BUTTON_SOUTH, SDL_GAMEPAD_BUTTON_EAST,
                                          SDL_GAMEPAD_BUTTON_WEST, SDL_GAMEPAD_BUTTON_NORTH,
                                          SDL_GAMEPAD_BUTTON_DPAD_UP, SDL_GAMEPAD_BUTTON_DPAD_DOWN,
                                          SDL_GAMEPAD_BUTTON_DPAD_LEFT, SDL_GAMEPAD_BUTTON_DPAD_RIGHT})
                    if (SDL_GetGamepadButton(gamepad, button))
                        return false;
            return true;
        }
        if (!gamepad_)
            return true;
        for (const auto button : {SDL_GAMEPAD_BUTTON_SOUTH, SDL_GAMEPAD_BUTTON_EAST,
                                  SDL_GAMEPAD_BUTTON_WEST, SDL_GAMEPAD_BUTTON_NORTH,
                                  SDL_GAMEPAD_BUTTON_DPAD_UP, SDL_GAMEPAD_BUTTON_DPAD_DOWN,
                                  SDL_GAMEPAD_BUTTON_DPAD_LEFT, SDL_GAMEPAD_BUTTON_DPAD_RIGHT})
            if (SDL_GetGamepadButton(gamepad_, button))
                return false;
        return true;
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

        const auto keySymbols = xcb_key_symbols_alloc(presentationConnection_);
        if (keySymbols) {
            const auto keycodes = xcb_key_symbols_get_keycode(keySymbols, XK_g);
            if (keycodes && keycodes[0] != XCB_NO_SYMBOL) {
                globalGuideKeycode_ = keycodes[0];
                globalGuideRoot_ = presentationRoot_;
                xcb_grab_key(presentationConnection_, 1, globalGuideRoot_,
                             XCB_MOD_MASK_CONTROL | XCB_MOD_MASK_1,
                             globalGuideKeycode_, XCB_GRAB_MODE_ASYNC,
                             XCB_GRAB_MODE_ASYNC);
                xcb_grab_key(presentationConnection_, 1, globalGuideRoot_,
                             XCB_MOD_MASK_CONTROL | XCB_MOD_MASK_1 | XCB_MOD_MASK_2,
                             globalGuideKeycode_, XCB_GRAB_MODE_ASYNC,
                             XCB_GRAB_MODE_ASYNC);
            }
            free(keycodes);
            xcb_key_symbols_free(keySymbols);
        }

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
            if (responseType == XCB_KEY_PRESS) {
                const auto *key = reinterpret_cast<const xcb_key_press_event_t *>(event);
                const uint16_t modifiers = key->state &
                    (XCB_MOD_MASK_SHIFT | XCB_MOD_MASK_LOCK | XCB_MOD_MASK_CONTROL |
                     XCB_MOD_MASK_1 | XCB_MOD_MASK_2 | XCB_MOD_MASK_3 | XCB_MOD_MASK_4 |
                     XCB_MOD_MASK_5);
                const uint16_t expected = XCB_MOD_MASK_CONTROL | XCB_MOD_MASK_1;
                if (key->detail == globalGuideKeycode_
                    && (modifiers == expected || modifiers == (expected | XCB_MOD_MASK_2)))
                    startGuide();
                else if (guideProcess_ && guideKeyboardActions_.contains(key->detail))
                    sendGuideKeyboardAction(guideKeyboardActions_.value(key->detail));
            } else if (responseType == XCB_PROPERTY_NOTIFY) {
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
    uint8_t globalGuideKeycode_ = XCB_NO_SYMBOL;
    xcb_window_t globalGuideRoot_ = XCB_WINDOW_NONE;
    xcb_atom_t presentationAtom_ = XCB_ATOM_NONE;
    QSocketNotifier *presentationNotifier_ = nullptr;
    bool luluPresented_ = false;
    uint32_t focusedWindow_ = 0;
    xcb_window_t targetWindow_ = XCB_WINDOW_NONE;
    uint32_t targetPid_ = 0;
    QProcess *guideProcess_ = nullptr;
    QTimer dbusDiscoveryTimer_;
    QTimer keyboardOwnershipTimer_;
    QHash<QString, DbusInputRelay *> dbusRelays_;
    QHash<SDL_JoystickID, SDL_Gamepad *> allGamepads_;
    QHash<uint8_t, QString> guideKeyboardActions_;
    QString guideOwnerComposite_;
    bool pendingGuide_ = false;
    bool guideChordConsumed_ = false;
    bool oskActive_ = false;
    bool oskRequestPending_ = false;
    bool rearmRequired_ = false;
    SDL_Gamepad *gamepad_ = nullptr;
    int gamepadSlot_ = 0;
    int navigationPlayer_ = 1;
    bool navigationAll_ = true;

    void closeGamepads()
    {
        const bool selectedIsTracked = gamepad_
            && allGamepads_.values().contains(gamepad_);
        for (auto *gamepad : allGamepads_)
            SDL_CloseGamepad(gamepad);
        allGamepads_.clear();
        if (gamepad_ && !selectedIsTracked)
            SDL_CloseGamepad(gamepad_);
        gamepad_ = nullptr;
    }
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
    QCoreApplication::setAttribute(Qt::AA_ShareOpenGLContexts);
    QtWebEngineQuick::initialize();
    QGuiApplication application(argc, argv);
    qmlRegisterType<MudosGlassItem>("Mudos.Poc", 1, 0, "MudosGlassItem");
    QQmlApplicationEngine engine;
    ControllerBridge controller(nullptr, &application);
    SystemStatusBridge systemStatus(&application);
    CatalogueModel catalogueModel(&application);
    RecentModel recentModel(&catalogueModel, &application);
    StoreBookmarkBridge storeBookmarks(&application);
    PluginStoreCardBridge pluginStoreCards(&application);
    engine.rootContext()->setContextProperty("controllerBridge", &controller);
    engine.rootContext()->setContextProperty("systemStatus", &systemStatus);
    // The native catalogue model is authoritative for the migrated Recent
    // consumer; Library and Store remain on their existing snapshot paths.
    engine.rootContext()->setContextProperty("catalogueModel", &catalogueModel);
    engine.rootContext()->setContextProperty("recentModel", &recentModel);
    engine.rootContext()->setContextProperty("bookmarkStore", &storeBookmarks);
    engine.rootContext()->setContextProperty("pluginStoreCardsBridge", &pluginStoreCards);
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
