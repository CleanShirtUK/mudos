#include <QGuiApplication>
#include <QDebug>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQmlPropertyMap>
#include <QQuickWindow>
#include <QUrl>
#include <QSocketNotifier>
#include <QProcess>
#include <QDBusInterface>
#include <QJsonDocument>
#include <QJsonObject>
#include <QVariant>
#include <QStringList>
#include <QFile>

#include <xcb/xcb.h>
#include <xcb/xtest.h>
#include <xcb/xcb_keysyms.h>
#include <X11/keysym.h>

#include <csignal>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <unistd.h>
#include <QHash>

namespace {

class GuideWindow final : public QObject
{
public:
    GuideWindow(QQuickWindow *window, uint32_t targetXid, uint32_t targetPid,
                const QString &providerMenuCommand, const QString &providerMenuLabel,
                bool edenProvider,
                QQmlPropertyMap *viewModel)
        : window_(window), targetXid_(targetXid), targetPid_(targetPid),
          providerMenuCommand_(providerMenuCommand), providerMenuLabel_(providerMenuLabel), edenProvider_(edenProvider), viewModel_(viewModel)
    {
    }

    bool prepare()
    {
        window_->create();
        if (!window_->winId())
            return false;
        const int flags = ::fcntl(STDIN_FILENO, F_GETFL, 0);
        if (flags < 0 || ::fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK) < 0)
            return false;
        inputNotifier_ = new QSocketNotifier(STDIN_FILENO, QSocketNotifier::Read, this);
        connect(inputNotifier_, &QSocketNotifier::activated, this, [this]() { readInput(); });
        return setProperty("GAMESCOPE_EXTERNAL_OVERLAY", 1);
    }

private:
    void readInput()
    {
        char buffer[256];
        while (const ssize_t count = ::read(STDIN_FILENO, buffer, sizeof(buffer))) {
            if (count < 0)
                break;
            inputBuffer_.append(buffer, count);
        }
        int newline = inputBuffer_.indexOf('\n');
        while (newline >= 0) {
            const QString command = QString::fromUtf8(inputBuffer_.left(newline)).trimmed();
            inputBuffer_.remove(0, newline + 1);
            handleCommand(command);
            newline = inputBuffer_.indexOf('\n');
        }
    }

    void handleCommand(const QString &command)
    {
        const QStringList parts = command.split(QChar(' '), Qt::SkipEmptyParts);
        const QString action = parts.value(0);
        qInfo() << "Guide input" << action << parts;
        QString edge = QStringLiteral("down");
        for (const QString &part : parts) {
            if (part.startsWith(QStringLiteral("edge=")))
                edge = part.mid(5);
        }
        if (action == QStringLiteral("reset_edges")) {
            releasePressed_.clear();
            return;
        }
        const bool guideAction = action == QStringLiteral("ui_up")
            || action == QStringLiteral("ui_down")
            || action == QStringLiteral("ui_accept")
            || action == QStringLiteral("ui_back")
            || action == QStringLiteral("ui_guide");
        if (guideAction) {
            const bool pressed = edge != QStringLiteral("up");
            releasePressed_.insert(action, pressed);
            if (pressed)
                return;
        }
        if (action == QStringLiteral("ui_up")) {
            viewModel_->insert("selection", 0);
        }
        else if (action == QStringLiteral("ui_down")) {
            const int actionCount = actionCountForModel();
            viewModel_->insert("selection", qMin(viewModel_->value("selection").toInt() + 1, actionCount - 1));
        }
        else if (action == QStringLiteral("ui_accept"))
        {
            const int selection = viewModel_->value("selection").toInt();
            if (viewModel_->value("confirmationPending").toBool()) {
                if (selection == 0) {
                    viewModel_->insert("confirmationPending", false);
                    viewModel_->insert("selection", 0);
                } else if (viewModel_->value("confirmationAction").toString() == QStringLiteral("Reboot System"))
                    powerAction(QStringLiteral("Reboot"));
                else if (viewModel_->value("confirmationAction").toString() == QStringLiteral("Shut Down System"))
                    powerAction(QStringLiteral("PowerOff"));
                return;
            }
            const int actionSelection = selection;
            if (viewModel_->value("shellContext").toBool() && actionSelection == 0)
                resetMudos();
            else if (viewModel_->value("shellContext").toBool() && (actionSelection == 1 || actionSelection == 2)) {
                viewModel_->insert("confirmationAction", actionSelection == 1
                                   ? QStringLiteral("Reboot System") : QStringLiteral("Shut Down System"));
                viewModel_->insert("confirmationPending", true);
                viewModel_->insert("selection", 1);
                return;
            } else if (actionSelection == 0)
                resetMudos();
            else if (viewModel_->value("providerMenuAvailable").toBool() && actionSelection == 1) {
                openProviderMenu();
            }
            else if (actionSelection == compatibilitySelection())
                switchCompatibilityMode();
            else
                if (edenProvider_)
                    terminateEden();
                else
                    sendDelete();
            QCoreApplication::quit();
        }
        else if (action == QStringLiteral("ui_back")) {
            if (viewModel_->value("confirmationPending").toBool()) {
                viewModel_->insert("confirmationPending", false);
                viewModel_->insert("selection", 0);
            } else {
                QCoreApplication::quit();
            }
        } else if (action == QStringLiteral("ui_guide")) {
            QCoreApplication::quit();
        }
    }

    int compatibilitySelection() const
    {
        if (!viewModel_->value("compatibilityModeAvailable").toBool())
            return -1;
        return viewModel_->value("providerMenuAvailable").toBool() ? 2 : 1;
    }

    int actionCountForModel() const
    {
        if (viewModel_->value("confirmationPending").toBool())
            return 2;
        if (viewModel_->value("shellContext").toBool())
            return viewModel_->value("devGlassActions").toBool() ? 5 : 3;
        return 2 + (viewModel_->value("providerMenuAvailable").toBool() ? 1 : 0)
            + (viewModel_->value("compatibilityModeAvailable").toBool() ? 1 : 0);
    }

    void switchCompatibilityMode()
    {
        const bool compatibility = viewModel_->value("compatibilityMode").toBool();
        QDBusInterface sessiond("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession",
                                "org.lulu.ConsoleSession", QDBusConnection::sessionBus());
        const auto reply = sessiond.call("SetInputMode",
                                         compatibility ? QStringLiteral("gamepad") : QStringLiteral("compat"));
        if (reply.type() == QDBusMessage::ErrorMessage) {
            qWarning() << "Input mode change failed" << reply.errorMessage();
            return;
        }
        viewModel_->insert("compatibilityMode", !compatibility);
    }

    bool setProperty(const char *name, uint32_t value)
    {
        auto *x11 = qGuiApp->nativeInterface<QNativeInterface::QX11Application>();
        if (!x11 || !x11->connection())
            return false;
        const auto cookie = xcb_intern_atom(x11->connection(), 0, std::strlen(name), name);
        auto *reply = xcb_intern_atom_reply(x11->connection(), cookie, nullptr);
        if (!reply)
            return false;
        xcb_change_property(x11->connection(), XCB_PROP_MODE_REPLACE, window_->winId(),
                            reply->atom, XCB_ATOM_CARDINAL, 32, 1, &value);
        free(reply);
        xcb_flush(x11->connection());
        return true;
    }
    void terminateEden()
    {
        const auto group = ::getpgid(static_cast<pid_t>(targetPid_));
        if (group <= 1)
            return;
        if (::kill(-group, SIGTERM) < 0)
            return;
        ::usleep(100000);
        if (::kill(-group, 0) == 0)
            ::kill(-group, SIGKILL);
    }


    void sendDelete()
    {
        auto *x11 = qGuiApp->nativeInterface<QNativeInterface::QX11Application>();
        if (!x11 || !x11->connection())
            return;
        const auto protocols = xcb_intern_atom(x11->connection(), 0,
                                               sizeof("WM_PROTOCOLS") - 1, "WM_PROTOCOLS");
        const auto deleteAtom = xcb_intern_atom(x11->connection(), 0,
                                                sizeof("WM_DELETE_WINDOW") - 1, "WM_DELETE_WINDOW");
        auto *protocolReply = xcb_intern_atom_reply(x11->connection(), protocols, nullptr);
        auto *deleteReply = xcb_intern_atom_reply(x11->connection(), deleteAtom, nullptr);
        if (!protocolReply || !deleteReply) {
            free(protocolReply);
            free(deleteReply);
            return;
        }
        xcb_client_message_event_t message{};
        message.response_type = XCB_CLIENT_MESSAGE;
        message.window = targetXid_;
        message.type = protocolReply->atom;
        message.format = 32;
        message.data.data32[0] = deleteReply->atom;
        message.data.data32[1] = XCB_CURRENT_TIME;
        xcb_send_event(x11->connection(), 0, targetXid_, XCB_EVENT_MASK_NO_EVENT,
                       reinterpret_cast<const char *>(&message));
        xcb_flush(x11->connection());
        free(protocolReply);
        free(deleteReply);
    }

    void resetMudos()
    {
        QDBusInterface sessiond("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession",
                                "org.lulu.ConsoleSession", QDBusConnection::sessionBus());
        sessiond.call("ResetMudos");
    }

    void powerAction(const QString &method)
    {
        QDBusInterface logind("org.freedesktop.login1", "/org/freedesktop/login1",
                              "org.freedesktop.login1.Manager", QDBusConnection::systemBus());
        const auto reply = logind.call(method, false);
        if (reply.type() == QDBusMessage::ErrorMessage)
            qWarning() << method << "failed" << reply.errorMessage();
        else
            QCoreApplication::quit();
    }
    bool sendPcsx2Hotkey()
    {
        auto *x11 = qGuiApp->nativeInterface<QNativeInterface::QX11Application>();
        if (!x11 || !x11->connection())
            return false;
        auto *connection = x11->connection();
        auto *keySymbols = xcb_key_symbols_alloc(connection);
        if (!keySymbols)
            return false;
        const auto keycodes = xcb_key_symbols_get_keycode(keySymbols, XK_F12);
        if (!keycodes || keycodes[0] == XCB_NO_SYMBOL)
        {
            free(keycodes);
            xcb_key_symbols_free(keySymbols);
            return false;
        }
        const auto setup = xcb_get_setup(connection);
        const auto screen = xcb_setup_roots_iterator(setup).data;
        xcb_set_input_focus(connection, XCB_INPUT_FOCUS_NONE, targetXid_, XCB_CURRENT_TIME);
        xcb_test_fake_input(connection, XCB_KEY_PRESS, keycodes[0], XCB_CURRENT_TIME,
                            screen->root, 0, 0, 0);
        xcb_test_fake_input(connection, XCB_KEY_RELEASE, keycodes[0], XCB_CURRENT_TIME,
                            screen->root, 0, 0, 0);
        xcb_flush(connection);
        free(keycodes);
        xcb_key_symbols_free(keySymbols);
        return true;
    }

    void openProviderMenu()
    {
        if (providerMenuLabel_ == QStringLiteral("Open Downloads")) {
            QDBusInterface sessiond("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession",
                                    "org.lulu.ConsoleSession", QDBusConnection::sessionBus());
            sessiond.call("RequestMudosDownloads");
            return;
        }
        if (providerMenuLabel_ == QStringLiteral("Open PCSX2 Menu")) {
            if (!sendPcsx2Hotkey())
                qWarning() << "PCSX2 provider menu hotkey failed";
            return;
        }

        const auto command = QProcess::splitCommand(providerMenuCommand_);
        if (command.isEmpty())
            return;
        QProcess providerProcess;
        providerProcess.start(command.constFirst(), command.mid(1));
        if (!providerProcess.waitForStarted(1000)
            || !providerProcess.waitForFinished(1000)) {
            qWarning() << "Provider menu command failed to start" << providerMenuCommand_;
        }
    }

    QQuickWindow *window_;
    uint32_t targetXid_;

    uint32_t targetPid_;
    QString providerMenuCommand_;
    QString providerMenuLabel_;
    bool edenProvider_;
    QQmlPropertyMap *viewModel_;
    QSocketNotifier *inputNotifier_ = nullptr;
    QByteArray inputBuffer_;
    QHash<QString, bool> releasePressed_;
};

} // namespace

int main(int argc, char **argv)
{
    if (argc < 3 || argc > 5)
        return EXIT_FAILURE;
    const auto targetXid = static_cast<uint32_t>(std::strtoul(argv[1], nullptr, 0));
    const auto targetPid = static_cast<uint32_t>(std::strtoul(argv[2], nullptr, 0));
    const auto providerMenuCommand = argc == 4 ? QString::fromLocal8Bit(argv[3]) : QString();
    auto providerMenuLabel = argc == 5 ? QString::fromLocal8Bit(argv[4]) : QStringLiteral("Provider Menu");
    bool edenProvider = false;
    auto effectiveProviderCommand = providerMenuCommand;
    bool compatibilityMode = false;
    bool shellContext = false;
    bool compatibilityModeAvailable = targetPid > 1;
    QString primaryId;
    QDBusInterface sessiond("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession",
                            "org.lulu.ConsoleSession", QDBusConnection::sessionBus());
    const auto stateReply = sessiond.call("GetState");
    if (stateReply.type() != QDBusMessage::ErrorMessage && !stateReply.arguments().isEmpty()) {
        const auto state = QJsonDocument::fromJson(
            stateReply.arguments().constFirst().toString().toUtf8()).object();
        compatibilityModeAvailable = state.value("lifecycle").toString() != QStringLiteral("shell")
            && targetPid > 1;
        shellContext = state.value("lifecycle").toString() != QStringLiteral("game");
        compatibilityMode = state.value("input_mode").toString() == QStringLiteral("compat");
        primaryId = state.value("primary_id").toString();
            if (primaryId == QStringLiteral("steam-store")) {
                effectiveProviderCommand = QStringLiteral("MUDOS_DOWNLOADS");
                providerMenuLabel = QStringLiteral("Open Downloads");
        } else if (primaryId.startsWith(QStringLiteral("local:ps2:"))) {
            effectiveProviderCommand = QStringLiteral("PCSX2_OPEN_PAUSE_MENU");
            providerMenuLabel = QStringLiteral("Open PCSX2 Menu");
        } else if (primaryId.startsWith(QStringLiteral("local:nes:"))
                   || primaryId.startsWith(QStringLiteral("local:genesis:"))) {
            effectiveProviderCommand = QStringLiteral("/usr/bin/retroarch --command MENU_TOGGLE");
            providerMenuLabel = QStringLiteral("Open RetroArch Menu");
        } else if (primaryId.startsWith(QStringLiteral("local:switch:"))) {
            edenProvider = true;
        }
    }

    QGuiApplication application(argc, argv);
    QQmlPropertyMap viewModel;
    viewModel.insert("selection", 0);
    viewModel.insert("providerMenuAvailable", !effectiveProviderCommand.isEmpty());
    viewModel.insert("compatibilityModeAvailable", compatibilityModeAvailable);
    viewModel.insert("compatibilityMode", compatibilityMode);
    viewModel.insert("shellContext", shellContext);
    viewModel.insert("confirmationPending", false);
    viewModel.insert("confirmationAction", QString());
    viewModel.insert("providerMenuLabel", providerMenuLabel);
    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty("guideModel", &viewModel);
    engine.load(QUrl::fromLocalFile(qEnvironmentVariable("LULU_GUIDE_UI_FILE",
                                                         "/opt/lulu/ui/MudosGuide.qml")));
    if (engine.rootObjects().isEmpty())
        return EXIT_FAILURE;
    auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
    if (!window)
        return EXIT_FAILURE;
    GuideWindow guide(window, targetXid, targetPid, effectiveProviderCommand, providerMenuLabel, edenProvider, &viewModel);
    if (!guide.prepare())
        return EXIT_FAILURE;
    window->show();
    return application.exec();
}
