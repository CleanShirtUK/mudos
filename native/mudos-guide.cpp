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
#include <QJsonArray>
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
                const QVariantList &actions,
                QQmlPropertyMap *viewModel)
        : window_(window), targetXid_(targetXid), targetPid_(targetPid),
          actions_(actions), viewModel_(viewModel)
    {
    }

    bool prepare()
    {
        window_->create();
        if (!window_->winId())
            return false;
        window_->show();
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
                } else {
                    if (executeAction(viewModel_->value("confirmationId").toString()))
                        QCoreApplication::quit();
                }
                return;
            }
            const int actionSelection = selection;
            const auto action = actionAt(actionSelection);
            if (action.value("confirm").toBool()) {
                viewModel_->insert("confirmationId", action.value("id"));
                viewModel_->insert("confirmationAction", action.value("label"));
                viewModel_->insert("confirmationPending", true);
                viewModel_->insert("selection", 1);
                return;
            }
            if (executeAction(action.value("id").toString()))
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
        } else if (action == QStringLiteral("ui_left") || action == QStringLiteral("ui_right")) {
            // The current Guide is a vertical action list. Consume horizontal
            // keys here so they cannot reach the delegated surface.
            return;
        }
    }

    int actionCountForModel() const
    {
        if (viewModel_->value("confirmationPending").toBool())
            return 2;
        return actions_.size();
    }

    QVariantMap actionAt(int index) const
    {
        return index >= 0 && index < actions_.size() ? actions_.at(index).toMap() : QVariantMap();
    }

    bool executeAction(const QString &id)
    {
        QDBusInterface consoled("org.lulu.Consoled", "/org/lulu/Console",
                                "org.lulu.Console", QDBusConnection::sessionBus());
        const auto reply = consoled.call("ExecuteGuideAction", id);
        if (reply.type() == QDBusMessage::ErrorMessage) {
            qWarning() << "Guide action failed" << id << reply.errorMessage();
            return false;
        }
        const QString target = reply.arguments().value(0).toString();
        if (target == "executed") return true;
        if (target == "window-delete") return sendDelete();
        if (target == "process-group-terminate") return terminateProcessGroup();
        if (target.startsWith("key:")) return sendKey(target.mid(4));
        if (target.startsWith("command:")) return runCommand(target.mid(8));
        qWarning() << "Guide action returned unusable target" << id << target;
        return false;
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
    bool terminateProcessGroup()
    {
        const auto group = ::getpgid(static_cast<pid_t>(targetPid_));
        if (group <= 1)
            return false;
        if (::kill(-group, SIGTERM) < 0)
            return false;
        ::usleep(100000);
        if (::kill(-group, 0) == 0)
            ::kill(-group, SIGKILL);
        return true;
    }


    bool sendDelete()
    {
        auto *x11 = qGuiApp->nativeInterface<QNativeInterface::QX11Application>();
        if (!x11 || !x11->connection())
            return false;
        const auto protocols = xcb_intern_atom(x11->connection(), 0,
                                               sizeof("WM_PROTOCOLS") - 1, "WM_PROTOCOLS");
        const auto deleteAtom = xcb_intern_atom(x11->connection(), 0,
                                                sizeof("WM_DELETE_WINDOW") - 1, "WM_DELETE_WINDOW");
        auto *protocolReply = xcb_intern_atom_reply(x11->connection(), protocols, nullptr);
        auto *deleteReply = xcb_intern_atom_reply(x11->connection(), deleteAtom, nullptr);
        if (!protocolReply || !deleteReply) {
            free(protocolReply);
            free(deleteReply);
            return false;
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
        return true;
    }

    bool sendKey(const QString &key)
    {
        auto *x11 = qGuiApp->nativeInterface<QNativeInterface::QX11Application>();
        if (!x11 || !x11->connection())
            return false;
        auto *connection = x11->connection();
        auto *keySymbols = xcb_key_symbols_alloc(connection);
        if (!keySymbols)
            return false;
        const auto keycodes = xcb_key_symbols_get_keycode(keySymbols,
                                                          key == QStringLiteral("F12") ? XK_F12 : XK_F12);
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

    bool runCommand(const QString &commandLine)
    {
        const auto command = QProcess::splitCommand(commandLine);
        if (command.isEmpty()) return false;
        return QProcess::startDetached(command.constFirst(), command.mid(1));
    }

    QQuickWindow *window_;
    uint32_t targetXid_;

    uint32_t targetPid_;
    QVariantList actions_;
    QQmlPropertyMap *viewModel_;
    QSocketNotifier *inputNotifier_ = nullptr;
    QByteArray inputBuffer_;
    QHash<QString, bool> releasePressed_;
};

} // namespace

int main(int argc, char **argv)
{
    if (argc < 3)
        return EXIT_FAILURE;
    const auto targetXid = static_cast<uint32_t>(std::strtoul(argv[1], nullptr, 0));
    const auto targetPid = static_cast<uint32_t>(std::strtoul(argv[2], nullptr, 0));
    QVariantList actions;
    QDBusInterface consoled("org.lulu.Consoled", "/org/lulu/Console",
                             "org.lulu.Console", QDBusConnection::sessionBus());
    const auto actionsReply = consoled.call("GetGuideActions");
    if (actionsReply.type() != QDBusMessage::ErrorMessage && !actionsReply.arguments().isEmpty()) {
        const auto array = QJsonDocument::fromJson(actionsReply.arguments().constFirst().toString().toUtf8()).array();
        for (const auto &value : array) {
            QVariantMap action;
            const auto object = value.toObject();
            for (auto it = object.begin(); it != object.end(); ++it)
                action.insert(it.key(), it.value().toVariant());
            actions.append(action);
        }
    }

    QGuiApplication application(argc, argv);
    QQmlPropertyMap viewModel;
    viewModel.insert("selection", 0);
    viewModel.insert("actions", actions);
    viewModel.insert("confirmationPending", false);
    viewModel.insert("confirmationAction", QString());
    viewModel.insert("confirmationId", QString());
    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty("guideModel", &viewModel);
    engine.load(QUrl::fromLocalFile(qEnvironmentVariable("LULU_GUIDE_UI_FILE",
                                                         "/opt/lulu/ui/MudosGuide.qml")));
    if (engine.rootObjects().isEmpty())
        return EXIT_FAILURE;
    auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
    if (!window)
        return EXIT_FAILURE;
    GuideWindow guide(window, targetXid, targetPid, actions, &viewModel);
    if (!guide.prepare())
        return EXIT_FAILURE;
    return application.exec();
}
