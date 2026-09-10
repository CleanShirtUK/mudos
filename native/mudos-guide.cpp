#include <QGuiApplication>
#include <QDebug>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQmlPropertyMap>
#include <QQuickWindow>
#include <QUrl>
#include <QSocketNotifier>

#include <xcb/xcb.h>

#include <csignal>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <unistd.h>

namespace {

class GuideWindow final : public QObject
{
public:
    GuideWindow(QQuickWindow *window, uint32_t targetXid, uint32_t targetPid,
                QQmlPropertyMap *viewModel)
        : window_(window), targetXid_(targetXid), targetPid_(targetPid), viewModel_(viewModel)
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
        if (command == QStringLiteral("ui_up"))
            viewModel_->insert("selection", 0);
        else if (command == QStringLiteral("ui_down"))
            return;
        else if (command == QStringLiteral("ui_accept"))
        {
            sendDelete();
            QCoreApplication::quit();
        }
        else if (command == QStringLiteral("ui_back") || command == QStringLiteral("ui_guide"))
            QCoreApplication::quit();
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

    QQuickWindow *window_;
    uint32_t targetXid_;
    uint32_t targetPid_;
    QQmlPropertyMap *viewModel_;
    QSocketNotifier *inputNotifier_ = nullptr;
    QByteArray inputBuffer_;
};

} // namespace

int main(int argc, char **argv)
{
    if (argc != 3)
        return EXIT_FAILURE;
    const auto targetXid = static_cast<uint32_t>(std::strtoul(argv[1], nullptr, 0));
    const auto targetPid = static_cast<uint32_t>(std::strtoul(argv[2], nullptr, 0));

    QGuiApplication application(argc, argv);
    QQmlPropertyMap viewModel;
    viewModel.insert("selection", 0);
    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty("guideModel", &viewModel);
    engine.load(QUrl::fromLocalFile(qEnvironmentVariable("LULU_GUIDE_UI_FILE",
                                                         "/opt/lulu/ui/MudosGuide.qml")));
    if (engine.rootObjects().isEmpty())
        return EXIT_FAILURE;
    auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
    if (!window)
        return EXIT_FAILURE;
    GuideWindow guide(window, targetXid, targetPid, &viewModel);
    if (!guide.prepare())
        return EXIT_FAILURE;
    window->show();
    return application.exec();
}
