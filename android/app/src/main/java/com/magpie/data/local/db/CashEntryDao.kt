package com.magpie.data.local.db

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface CashEntryDao {
    @Insert
    suspend fun insert(entry: PendingCashEntryEntity): Long

    @Query("SELECT * FROM pending_cash_entries ORDER BY createdAtMs")
    suspend fun getAllPending(): List<PendingCashEntryEntity>

    @Query("SELECT COUNT(*) FROM pending_cash_entries")
    fun observePendingCount(): Flow<Int>

    @Delete
    suspend fun delete(entry: PendingCashEntryEntity)
}
