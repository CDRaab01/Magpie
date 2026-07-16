package com.magpie.data.local.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction

@Dao
interface TransactionCacheDao {

    @Query("SELECT * FROM cached_transactions ORDER BY position")
    suspend fun getAll(): List<CachedTransactionEntity>

    @Query("DELETE FROM cached_transactions")
    suspend fun clear()

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(rows: List<CachedTransactionEntity>)

    /** Swap the whole mirror for a freshly-fetched page (the cache only ever holds one page). */
    @Transaction
    suspend fun replaceAll(rows: List<CachedTransactionEntity>) {
        clear()
        insertAll(rows)
    }
}
