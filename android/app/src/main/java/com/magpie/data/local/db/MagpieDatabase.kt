package com.magpie.data.local.db

import androidx.room.Database
import androidx.room.RoomDatabase

@Database(
    entities = [PendingCashEntryEntity::class, CachedTransactionEntity::class],
    version = 2,
    exportSchema = false,
)
abstract class MagpieDatabase : RoomDatabase() {
    abstract fun cashEntryDao(): CashEntryDao
    abstract fun transactionCacheDao(): TransactionCacheDao
}
