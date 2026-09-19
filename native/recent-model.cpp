#include "recent-model.h"

#include "catalogue-model.h"

#include <algorithm>
#include <QVariant>

RecentModel::RecentModel(CatalogueModel *source, QObject *parent)
    : QAbstractListModel(parent), source_(source)
{
    Q_ASSERT(source_);
    connect(source_, &QAbstractItemModel::modelReset, this, &RecentModel::rebuild);
    connect(source_, &QAbstractItemModel::rowsInserted,
            this, &RecentModel::sourceRowsInserted);
    connect(source_, &QAbstractItemModel::rowsAboutToBeRemoved,
            this, &RecentModel::sourceRowsAboutToBeRemoved);
    connect(source_, &QAbstractItemModel::rowsRemoved,
            this, &RecentModel::sourceRowsRemoved);
    connect(source_, &QAbstractItemModel::dataChanged,
            this, &RecentModel::sourceDataChanged);
    rebuild();
}

int RecentModel::rowCount(const QModelIndex &parent) const
{
    return parent.isValid() ? 0 : gameIds_.size();
}

QVariant RecentModel::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || index.row() < 0 || index.row() >= gameIds_.size())
        return {};
    const QVariantMap record = source_->game(gameIds_.at(index.row()));
    const QByteArray roleName = source_->roleNames().value(role);
    return roleName.isEmpty() ? QVariant() : record.value(QString::fromLatin1(roleName));
}

QHash<int, QByteArray> RecentModel::roleNames() const
{
    return source_->roleNames();
}

int RecentModel::indexOfGame(const QString &gameId) const
{
    return gameIds_.indexOf(gameId);
}

QString RecentModel::gameIdAt(int row) const
{
    return row >= 0 && row < gameIds_.size() ? gameIds_.at(row) : QString();
}

bool RecentModel::eligible(const QString &gameId) const
{
    const QVariantMap record = source_->game(gameId);
    if (record.isEmpty()
        || record.value(QStringLiteral("install_state")).toString() != QStringLiteral("installed")
        || record.value(QStringLiteral("last_played")).toLongLong() <= 0)
        return false;
    const QString installedGameId = record.value(QStringLiteral("installed_game_id")).toString();
    if (installedGameId.isEmpty())
        return true;
    const QVariantMap linked = source_->game(installedGameId);
    return linked.isEmpty()
        || linked.value(QStringLiteral("install_state")).toString() != QStringLiteral("installed");
}

qint64 RecentModel::lastPlayed(const QString &gameId) const
{
    return source_->game(gameId).value(QStringLiteral("last_played")).toLongLong();
}

bool RecentModel::comesBefore(const QString &left, const QString &right) const
{
    const qint64 leftPlayed = lastPlayedById_.value(left, lastPlayed(left));
    const qint64 rightPlayed = lastPlayedById_.value(right, lastPlayed(right));
    if (leftPlayed != rightPlayed)
        return leftPlayed > rightPlayed;
    return left < right;
}

int RecentModel::sortedInsertRow(const QString &gameId) const
{
    int row = 0;
    while (row < gameIds_.size() && !comesBefore(gameId, gameIds_.at(row)))
        ++row;
    return row;
}

void RecentModel::insertGame(const QString &gameId)
{
    const int row = sortedInsertRow(gameId);
    if (row >= kMaximumEntries)
        return;
    beginInsertRows({}, row, row);
    gameIds_.insert(row, gameId);
    lastPlayedById_.insert(gameId, lastPlayed(gameId));
    endInsertRows();
    if (gameIds_.size() > kMaximumEntries)
        removeGame(gameIds_.constLast());
}

void RecentModel::removeGame(const QString &gameId)
{
    const int row = gameIds_.indexOf(gameId);
    if (row < 0)
        return;
    beginRemoveRows({}, row, row);
    gameIds_.removeAt(row);
    lastPlayedById_.remove(gameId);
    endRemoveRows();
}

void RecentModel::rebuild()
{
    beginResetModel();
    gameIds_.clear();
    lastPlayedById_.clear();
    for (int row = 0; row < source_->rowCount(); ++row) {
        const QString gameId = source_->data(source_->index(row, 0), CatalogueModel::GameIdRole).toString();
        if (eligible(gameId)) {
            gameIds_.append(gameId);
            lastPlayedById_.insert(gameId, lastPlayed(gameId));
        }
    }
    std::sort(gameIds_.begin(), gameIds_.end(), [this](const QString &left, const QString &right) {
        return comesBefore(left, right);
    });
    while (gameIds_.size() > kMaximumEntries) {
        lastPlayedById_.remove(gameIds_.constLast());
        gameIds_.removeLast();
    }
    endResetModel();
}

void RecentModel::sourceRowsInserted(const QModelIndex &, int first, int last)
{
    for (int row = first; row <= last; ++row) {
        const QString gameId = source_->data(source_->index(row, 0), CatalogueModel::GameIdRole).toString();
        if (eligible(gameId))
            insertGame(gameId);
    }
}

void RecentModel::sourceRowsAboutToBeRemoved(const QModelIndex &, int first, int last)
{
    QStringList removed;
    for (int row = first; row <= last; ++row)
        removed.append(source_->data(source_->index(row, 0), CatalogueModel::GameIdRole).toString());
    for (const QString &gameId : removed)
        removeGame(gameId);
}

void RecentModel::sourceRowsRemoved(const QModelIndex &, int, int)
{
    // Entries below the public cap are intentionally not retained in
    // gameIds_. Rebuild after a source removal so the next eligible history
    // entry can fill the Recent rail.
    rebuild();
}

void RecentModel::sourceDataChanged(const QModelIndex &topLeft, const QModelIndex &bottomRight,
                                    const QList<int> &roles)
{
    for (int sourceRow = topLeft.row(); sourceRow <= bottomRight.row(); ++sourceRow) {
        const QString gameId = source_->data(source_->index(sourceRow, 0), CatalogueModel::GameIdRole).toString();
        const bool wasRecent = gameIds_.contains(gameId);
        const bool isRecent = eligible(gameId);
        if (!wasRecent && isRecent) {
            insertGame(gameId);
            continue;
        }
        if (wasRecent && !isRecent) {
            removeGame(gameId);
            continue;
        }
        if (!isRecent)
            continue;

        const int oldRow = gameIds_.indexOf(gameId);
        const qint64 oldPlayed = lastPlayedById_.value(gameId);
        const qint64 newPlayed = lastPlayed(gameId);
        lastPlayedById_[gameId] = newPlayed;
        const int destination = sortedInsertRow(gameId);
        int targetRow = destination;
        if (destination > oldRow)
            targetRow = destination - 1;
        if (targetRow != oldRow) {
            const int destinationChild = targetRow > oldRow ? targetRow + 1 : targetRow;
            if (beginMoveRows({}, oldRow, oldRow, {}, destinationChild)) {
                gameIds_.move(oldRow, targetRow);
                endMoveRows();
            }
        }
        const int finalRow = gameIds_.indexOf(gameId);
        QVector<int> changedRoles;
        for (const int role : roles)
            if (role != CatalogueModel::GameIdRole)
                changedRoles.append(role);
        if (oldPlayed != newPlayed && !changedRoles.contains(CatalogueModel::LastPlayedRole))
            changedRoles.append(CatalogueModel::LastPlayedRole);
        if (!changedRoles.isEmpty())
            emit dataChanged(index(finalRow, 0), index(finalRow, 0), changedRoles);
    }
}
