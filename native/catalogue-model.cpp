#include "catalogue-model.h"

#include <QDBusConnection>
#include <QDBusArgument>
#include <QDBusInterface>
#include <QDBusMessage>
#include <QDBusPendingCall>
#include <QDBusPendingReply>
#include <QDBusPendingCallWatcher>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTimer>

namespace {
const QString service = QStringLiteral("org.lulu.Consoled");
const QString path = QStringLiteral("/org/lulu/Console");
const QString iface = QStringLiteral("org.lulu.Console");

const QVector<QPair<const char *, const char *>> roleFields = {
    {"game_id", "game_id"}, {"provider", "provider"}, {"provider_id", "provider_id"},
    {"title", "title"}, {"platform", "platform"}, {"install_state", "install_state"},
    {"launchable", "launchable"}, {"install_dir", "install_dir"}, {"artwork_url", "artwork_url"},
    {"last_played", "last_played"}, {"runtime", "runtime"}, {"platform_label", "platform_label"},
    {"source_title", "source_title"}, {"normalized_search_title", "normalized_search_title"},
    {"metadata_provider", "metadata_provider"}, {"metadata_game_id", "metadata_game_id"},
    {"canonical_title", "canonical_title"}, {"match_status", "match_status"},
    {"match_method", "match_method"}, {"match_confidence", "match_confidence"},
    {"match_locked", "match_locked"}, {"metadata_checked_at", "metadata_checked_at"},
    {"display_title_override", "display_title_override"}, {"artwork_suppressed", "artwork_suppressed"},
    {"availability_state", "availability_state"}, {"provider_record_id", "provider_record_id"},
    {"content_identity", "content_identity"}, {"catalogue_source", "catalogue_source"},
    {"genres", "genres"}, {"game_modes", "game_modes"},
    {"release_date", "release_date"}, {"release_year", "release_year"},
    {"total_playtime", "total_playtime"}, {"local_multiplayer", "local_multiplayer"},
    {"online_multiplayer", "online_multiplayer"}, {"game_mode", "game_mode"},
    {"protondb_rating", "protondb_rating"}, {"last_seen_at", "last_seen_at"},
    {"last_synced_at", "last_synced_at"}, {"artwork_source_url", "artwork_source_url"},
    {"metadata_resolver_version", "metadata_resolver_version"},
    {"installed_game_id", "installed_game_id"},
    {"developer", "developer"}, {"publisher", "publisher"},
};
}

CatalogueModel::CatalogueModel(QObject *parent) : QAbstractListModel(parent)
{
    int role = GameIdRole;
    for (const auto &[name, field] : roleFields) {
        roles_.insert(role++, QByteArray(name));
        Q_UNUSED(field);
    }
    QDBusConnection::sessionBus().connect(
        service, path, iface, QStringLiteral("CatalogueGenerationChanged"),
        this, SLOT(onCatalogueGenerationChanged(qulonglong)));
    QTimer::singleShot(0, this, &CatalogueModel::requestSnapshot);
}

int CatalogueModel::rowCount(const QModelIndex &parent) const
{
    return parent.isValid() ? 0 : rows_.size();
}

QVariant CatalogueModel::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || index.row() < 0 || index.row() >= rows_.size())
        return {};
    const auto iterator = rows_.at(index.row()).constFind(QString::fromLatin1(roles_.value(role)));
    return iterator == rows_.at(index.row()).constEnd() ? QVariant() : iterator.value();
}

QHash<int, QByteArray> CatalogueModel::roleNames() const
{
    return roles_;
}

QVariantMap CatalogueModel::game(const QString &gameId) const
{
    const int row = rowById_.value(gameId, -1);
    return row >= 0 ? rows_.at(row) : QVariantMap();
}

void CatalogueModel::setError(QString *error, const QString &message) const
{
    if (error)
        *error = message;
}

bool CatalogueModel::loadSnapshot(qulonglong generation, const QByteArray &json, QString *error)
{
    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(json, &parseError);
    if (!document.isArray()) {
        setError(error, parseError.errorString());
        return false;
    }

    QVector<QVariantMap> next;
    QHash<QString, int> nextIndex;
    for (const QJsonValue &value : document.array()) {
        if (!value.isObject()) {
            setError(error, QStringLiteral("snapshot contains a non-object record"));
            return false;
        }
        const QVariantMap record = value.toObject().toVariantMap();
        const QString gameId = record.value(QStringLiteral("game_id")).toString();
        if (gameId.isEmpty() || nextIndex.contains(gameId)) {
            setError(error, QStringLiteral("snapshot contains duplicate or empty game_id"));
            return false;
        }
        nextIndex.insert(gameId, next.size());
        next.append(record);
    }

    beginResetModel();
    rows_ = std::move(next);
    rowById_ = std::move(nextIndex);
    generation_ = generation;
    endResetModel();
    emit generationChanged();
    return true;
}

int CatalogueModel::roleForField(const QString &field) const
{
    for (auto iterator = roles_.cbegin(); iterator != roles_.cend(); ++iterator) {
        if (iterator.value() == field)
            return iterator.key();
    }
    return -1;
}

bool CatalogueModel::applyDelta(const QVariantMap &delta, QString *error)
{
    const QString kind = delta.value(QStringLiteral("kind")).toString();
    const QString gameId = delta.value(QStringLiteral("game_id")).toString();
    if (gameId.isEmpty()) {
        setError(error, QStringLiteral("delta has no game_id"));
        return false;
    }
    const int oldRow = rowById_.value(gameId, -1);
    if (kind == QStringLiteral("insert")) {
        if (oldRow >= 0) {
            setError(error, QStringLiteral("duplicate insert: ") + gameId);
            return false;
        }
        const QVariantMap record = delta.value(QStringLiteral("after")).toMap();
        beginInsertRows({}, rows_.size(), rows_.size());
        rowById_.insert(gameId, rows_.size());
        rows_.append(record);
        endInsertRows();
        return true;
    }
    if (kind == QStringLiteral("remove")) {
        if (oldRow < 0) {
            setError(error, QStringLiteral("missing removal: ") + gameId);
            return false;
        }
        beginRemoveRows({}, oldRow, oldRow);
        rows_.removeAt(oldRow);
        rowById_.remove(gameId);
        for (int row = oldRow; row < rows_.size(); ++row)
            rowById_[rows_.at(row).value(QStringLiteral("game_id")).toString()] = row;
        endRemoveRows();
        return true;
    }
    if (kind != QStringLiteral("update") || oldRow < 0) {
        setError(error, QStringLiteral("invalid update: ") + gameId);
        return false;
    }
    const QVariantMap after = delta.value(QStringLiteral("after")).toMap();
    rows_[oldRow] = after;
    QVector<int> changedRoles;
    for (const QVariant &field : delta.value(QStringLiteral("changed_fields")).toList()) {
        const int role = roleForField(field.toString());
        if (role >= 0)
            changedRoles.append(role);
    }
    const QModelIndex modelIndex = index(oldRow, 0);
    emit dataChanged(modelIndex, modelIndex, changedRoles);
    return true;
}

bool CatalogueModel::applyChanges(qulonglong expectedGeneration, const QByteArray &json, QString *error)
{
    if (generation_ != expectedGeneration) {
        setError(error, QStringLiteral("generation mismatch"));
        return false;
    }
    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(json, &parseError);
    if (!document.isArray()) {
        setError(error, parseError.errorString());
        return false;
    }
    for (const QJsonValue &batchValue : document.array()) {
        const QJsonObject batch = batchValue.toObject();
        const qulonglong batchGeneration = batch.value(QStringLiteral("generation")).toVariant().toULongLong();
        if (batchGeneration != generation_ + 1) {
            setError(error, QStringLiteral("non-contiguous generation"));
            return false;
        }
        for (const QJsonValue &deltaValue : batch.value(QStringLiteral("deltas")).toArray()) {
            if (!applyDelta(deltaValue.toObject().toVariantMap(), error))
                return false;
        }
        generation_ = batchGeneration;
        emit generationChanged();
    }
    return true;
}

void CatalogueModel::requestSnapshot()
{
    if (snapshotInFlight_)
        return;
    snapshotInFlight_ = true;
    auto *interface = new QDBusInterface(service, path, iface, QDBusConnection::sessionBus(), this);
    auto *watcher = new QDBusPendingCallWatcher(interface->asyncCall(QStringLiteral("GetCatalogueSnapshot")), this);
    connect(watcher, &QDBusPendingCallWatcher::finished, this, &CatalogueModel::onSnapshotFinished);
}

void CatalogueModel::requestChanges()
{
    if (snapshotInFlight_ || changesInFlight_ || pendingGeneration_ <= generation_)
        return;
    changesInFlight_ = true;
    auto *interface = new QDBusInterface(service, path, iface, QDBusConnection::sessionBus(), this);
    auto *watcher = new QDBusPendingCallWatcher(
        interface->asyncCall(QStringLiteral("GetCatalogueChanges"), generation_), this);
    connect(watcher, &QDBusPendingCallWatcher::finished, this, &CatalogueModel::onChangesFinished);
}

void CatalogueModel::onCatalogueGenerationChanged(qulonglong generation)
{
    pendingGeneration_ = qMax(pendingGeneration_, generation);
    requestChanges();
}

void CatalogueModel::onSnapshotFinished(QDBusPendingCallWatcher *watcher)
{
    snapshotInFlight_ = false;
    const QDBusPendingReply<> reply = *watcher;
    watcher->deleteLater();
    if (reply.isError()) {
        emit synchronizationFailed(reply.error().message());
        QTimer::singleShot(1000, this, &CatalogueModel::requestSnapshot);
        return;
    }
    const QDBusMessage message = reply.reply();
    if (message.arguments().isEmpty()) {
        QTimer::singleShot(1000, this, &CatalogueModel::requestSnapshot);
        return;
    }
    const QDBusArgument structure = qvariant_cast<QDBusArgument>(message.arguments().constFirst());
    qulonglong generation = 0;
    QString payload;
    structure.beginStructure();
    structure >> generation >> payload;
    structure.endStructure();
    QString error;
    if (!loadSnapshot(generation, payload.toUtf8(), &error)) {
        emit synchronizationFailed(error);
        QTimer::singleShot(1000, this, &CatalogueModel::requestSnapshot);
        return;
    }
    pendingGeneration_ = qMax(pendingGeneration_, generation_);
    requestChanges();
}

void CatalogueModel::onChangesFinished(QDBusPendingCallWatcher *watcher)
{
    changesInFlight_ = false;
    const QDBusPendingReply<> reply = *watcher;
    watcher->deleteLater();
    if (reply.isError()) {
        emit synchronizationFailed(reply.error().message());
        QTimer::singleShot(1000, this, &CatalogueModel::requestChanges);
        return;
    }
    const QDBusMessage message = reply.reply();
    if (message.arguments().isEmpty()) {
        QTimer::singleShot(1000, this, &CatalogueModel::requestChanges);
        return;
    }
    const QDBusArgument structure = qvariant_cast<QDBusArgument>(message.arguments().constFirst());
    bool resyncRequired = false;
    QString payload;
    structure.beginStructure();
    structure >> resyncRequired >> payload;
    structure.endStructure();
    if (resyncRequired) {
        requestSnapshot();
        return;
    }
    QString error;
    if (!applyChanges(generation_, payload.toUtf8(), &error)) {
        emit synchronizationFailed(error);
        requestSnapshot();
        return;
    }
    requestChanges();
}
