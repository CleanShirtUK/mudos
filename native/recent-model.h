#pragma once

#include <QAbstractListModel>
#include <QHash>
#include <QStringList>

class CatalogueModel;

class RecentModel final : public QAbstractListModel
{
    Q_OBJECT

public:
    explicit RecentModel(CatalogueModel *source, QObject *parent = nullptr);

    int rowCount(const QModelIndex &parent = {}) const override;
    QVariant data(const QModelIndex &index, int role = Qt::DisplayRole) const override;
    QHash<int, QByteArray> roleNames() const override;

    Q_INVOKABLE int indexOfGame(const QString &gameId) const;
    Q_INVOKABLE QString gameIdAt(int row) const;

private slots:
    void rebuild();
    void sourceRowsInserted(const QModelIndex &parent, int first, int last);
    void sourceRowsAboutToBeRemoved(const QModelIndex &parent, int first, int last);
    void sourceDataChanged(const QModelIndex &topLeft, const QModelIndex &bottomRight,
                           const QList<int> &roles = {});

private:
    bool eligible(const QString &gameId) const;
    qint64 lastPlayed(const QString &gameId) const;
    bool comesBefore(const QString &left, const QString &right) const;
    int sortedInsertRow(const QString &gameId) const;
    void insertGame(const QString &gameId);
    void removeGame(const QString &gameId);

    CatalogueModel *source_;
    QStringList gameIds_;
    QHash<QString, qint64> lastPlayedById_;
};
