#include "mudos-display-underlay.h"

#include <QMetaObject>
#include <QSGSimpleTextureNode>
#include <QSGTexture>
#include <QSGTextureProvider>

#include <pipewire/pipewire.h>
#include <spa/param/video/format-utils.h>
#include <spa/param/video/raw.h>
#include <spa/utils/result.h>

#include <algorithm>
#include <cstring>
#include <mutex>
#include <thread>

class MudosDisplayUnderlay::TextureProvider final : public QSGTextureProvider
{
public:
    QSGTexture *texture() const override { return texture_; }

    void setTexture(QSGTexture *texture)
    {
        if (texture_ == texture)
            return;
        texture_ = texture;
        emit textureChanged();
    }

private:
    QSGTexture *texture_ = nullptr;
};

class MudosDisplayUnderlay::Capture final
{
public:
    explicit Capture(MudosDisplayUnderlay *owner) : owner_(owner) {}
    ~Capture() { stop(); }

    void start()
    {
        if (thread_.joinable())
            return;
        thread_ = std::thread([this] { run(); });
    }

    void stop()
    {
        if (loop_) {
            pw_thread_loop_lock(loop_);
            running_ = false;
            pw_thread_loop_signal(loop_, false);
            pw_thread_loop_unlock(loop_);
        }
        if (thread_.joinable())
            thread_.join();
    }

private:
    static void process(void *data)
    {
        auto *self = static_cast<Capture *>(data);
        auto *buffer = pw_stream_dequeue_buffer(self->stream_);
        if (!buffer || !buffer->buffer)
            return;

        const auto &spa = buffer->buffer->datas[0];
        if (!spa.data || !self->width_ || !self->height_ || spa.chunk->stride <= 0) {
            pw_stream_queue_buffer(self->stream_, buffer);
            return;
        }

        QImage frame(static_cast<int>(self->width_), static_cast<int>(self->height_),
                     QImage::Format_RGBA8888);
        const auto *source = static_cast<const unsigned char *>(spa.data) + spa.chunk->offset;
        const int sourceStride = spa.chunk->stride;
        self->sourceStride_ = sourceStride;
        if (!self->loggedSource_) {
            self->loggedSource_ = true;
            qInfo() << "MUDOS_DISPLAY_UNDERLAY_BUFFER"
                    << "offset=" << spa.chunk->offset
                    << "size=" << spa.chunk->size
                    << "stride=" << sourceStride
                    << "firstBGRx=" << source[0] << source[1] << source[2] << source[3];
        }
        const int destinationStride = frame.bytesPerLine();
        for (uint32_t row = 0; row < self->height_; ++row) {
            const auto *input = source + row * sourceStride;
            auto *output = frame.scanLine(static_cast<int>(row));
            for (uint32_t column = 0; column < self->width_; ++column) {
                // PipeWire BGRx is explicitly converted to Qt's byte-ordered
                // RGBA8888. The x byte is padding, never alpha.
                output[column * 4 + 0] = input[column * 4 + 2];
                output[column * 4 + 1] = input[column * 4 + 1];
                output[column * 4 + 2] = input[column * 4 + 0];
                output[column * 4 + 3] = 0xff;
            }
        }

        pw_stream_queue_buffer(self->stream_, buffer);
        QMetaObject::invokeMethod(self->owner_, [owner = self->owner_, frame = std::move(frame), sourceStride] {
            owner->acceptFrame(frame, sourceStride);
        }, Qt::QueuedConnection);
    }

    static void stateChanged(void *data, pw_stream_state, pw_stream_state state, const char *error)
    {
        auto *self = static_cast<Capture *>(data);
        if (error)
            qWarning("display underlay PipeWire: %s", error);
        if (state == PW_STREAM_STATE_ERROR || state == PW_STREAM_STATE_UNCONNECTED) {
            self->running_ = false;
            if (self->loop_)
                pw_thread_loop_signal(self->loop_, false);
        }
    }

    static void paramChanged(void *data, uint32_t id, const spa_pod *param)
    {
        auto *self = static_cast<Capture *>(data);
        if (!param || id != SPA_PARAM_Format)
            return;
        spa_video_info_raw info{};
        if (spa_format_video_raw_parse(param, &info) < 0)
            return;
        self->width_ = info.size.width;
        self->height_ = info.size.height;
    }

    static constexpr pw_stream_events events_ = {
        PW_VERSION_STREAM_EVENTS,
        nullptr,
        stateChanged,
        nullptr,
        nullptr,
        paramChanged,
        nullptr,
        nullptr,
        process,
        nullptr,
        nullptr,
        nullptr,
    };

    void run()
    {
        pw_init(nullptr, nullptr);
        loop_ = pw_thread_loop_new("lulu-display-underlay", nullptr);
        if (!loop_)
            return;
        auto *context = pw_context_new(pw_thread_loop_get_loop(loop_), nullptr, 0);
        if (!context)
            return;
        auto *core = pw_context_connect(context, nullptr, 0);
        if (!core)
            return;

        auto *props = pw_properties_new(
            PW_KEY_MEDIA_TYPE, "Video",
            PW_KEY_MEDIA_CATEGORY, "Capture",
            PW_KEY_MEDIA_ROLE, "Screen",
            PW_KEY_TARGET_OBJECT, "gamescope",
            nullptr);
        stream_ = pw_stream_new(core, "lulu-display-underlay", props);
        if (!stream_)
            return;
        pw_stream_add_listener(stream_, &streamHook_, &events_, this);

        uint8_t buffer[2048];
        spa_pod_builder builder = SPA_POD_BUILDER_INIT(buffer, sizeof(buffer));
        const spa_pod *params[1];
        spa_rectangle size = SPA_RECTANGLE(1, 1);
        spa_rectangle minSize = SPA_RECTANGLE(1, 1);
        spa_rectangle maxSize = SPA_RECTANGLE(UINT32_MAX, UINT32_MAX);
        spa_fraction rate = SPA_FRACTION(0, 1);
        params[0] = static_cast<const spa_pod *>(spa_pod_builder_add_object(
            &builder, SPA_TYPE_OBJECT_Format, SPA_PARAM_EnumFormat,
            SPA_FORMAT_mediaType, SPA_POD_Id(SPA_MEDIA_TYPE_video),
            SPA_FORMAT_mediaSubtype, SPA_POD_Id(SPA_MEDIA_SUBTYPE_raw),
            SPA_FORMAT_VIDEO_format, SPA_POD_Id(SPA_VIDEO_FORMAT_BGRx),
            SPA_FORMAT_VIDEO_size, SPA_POD_CHOICE_RANGE_Rectangle(&size, &minSize, &maxSize),
            SPA_FORMAT_VIDEO_framerate, SPA_POD_Fraction(&rate)));

        running_ = pw_stream_connect(stream_, PW_DIRECTION_INPUT, PW_ID_ANY,
                                     static_cast<pw_stream_flags>(PW_STREAM_FLAG_AUTOCONNECT
                                         | PW_STREAM_FLAG_MAP_BUFFERS),
                                     params, 1) == 0;
        if (running_)
            pw_thread_loop_start(loop_);
        if (running_) {
            pw_thread_loop_lock(loop_);
            pw_thread_loop_wait(loop_);
            pw_thread_loop_unlock(loop_);
        }
        if (stream_)
            pw_stream_destroy(stream_);
        pw_core_disconnect(core);
        pw_context_destroy(context);
        pw_thread_loop_destroy(loop_);
        stream_ = nullptr;
        loop_ = nullptr;
    }

    MudosDisplayUnderlay *owner_;
    pw_thread_loop *loop_ = nullptr;
    pw_stream *stream_ = nullptr;
    spa_hook streamHook_{};
    std::thread thread_;
    std::atomic<bool> running_{false};
    uint32_t width_ = 0;
    uint32_t height_ = 0;
    int sourceStride_ = 0;
    bool loggedSource_ = false;
};

constexpr pw_stream_events MudosDisplayUnderlay::Capture::events_;

MudosDisplayUnderlay::MudosDisplayUnderlay(QQuickItem *parent)
    : QQuickItem(parent), capture_(std::make_unique<Capture>(this)),
      provider_(std::make_unique<TextureProvider>())
{
    setFlag(ItemHasContents, true);
    connect(this, &QQuickItem::visibleChanged, this, [this] {
        if (isVisible())
            capture_->start();
        else
            capture_->stop();
    });
    if (isVisible())
        capture_->start();
}

MudosDisplayUnderlay::~MudosDisplayUnderlay() = default;

void MudosDisplayUnderlay::acceptFrame(const QImage &frame, int sourceStride)
{
    const bool sizeChanged = frameSize_ != frame.size();
    const bool availabilityChanged = !available_;
    frame_ = frame;
    frameSize_ = frame.size();
    ++frameCount_;
    const bool strideChanged = frameStride_ != sourceStride;
    frameStride_ = sourceStride;
    available_ = true;
    if (!loggedFirstFrame_) {
        loggedFirstFrame_ = true;
        qInfo() << "MUDOS_DISPLAY_UNDERLAY_FRAME"
                << "size=" << frame.size()
                << "format=BGRx->RGBA8888"
                << "sourceStride=" << sourceStride
                << "qtStride=" << frame.bytesPerLine()
                << "diagnostic=" << diagnosticMode_;
        frame_.save(QStringLiteral("/tmp/mudos-display-underlay-raw-first.png"));
    }
    if (sizeChanged)
        emit frameSizeChanged();
    if (strideChanged)
        emit frameStrideChanged();
    if (frameCount_ == 30)
        frame_.save(QStringLiteral("/tmp/mudos-display-underlay-raw.png"));
    if (availabilityChanged)
        emit availableChanged();
    update();
}

bool MudosDisplayUnderlay::isTextureProvider() const
{
    return true;
}

QSGTextureProvider *MudosDisplayUnderlay::textureProvider() const
{
    return provider_.get();
}

QSGNode *MudosDisplayUnderlay::updatePaintNode(QSGNode *oldNode, UpdatePaintNodeData *)
{
    auto *node = static_cast<QSGSimpleTextureNode *>(oldNode);
    if (!node) {
        node = new QSGSimpleTextureNode;
        node->setOwnsTexture(true);
    }
    if (frame_.isNull() || !window())
        return node;
    auto *texture = window()->createTextureFromImage(frame_);
    if (!texture)
        return node;
    provider_->setTexture(texture);
    node->setTexture(texture);
    node->setRect(boundingRect());
    return node;
}
