package com.magpie.di

import android.content.Context
import androidx.room.Room
import com.magpie.data.local.db.CashEntryDao
import com.magpie.data.local.db.MagpieDatabase
import com.magpie.data.local.db.TransactionCacheDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): MagpieDatabase =
        Room.databaseBuilder(context, MagpieDatabase::class.java, "magpie.db")
            // The DB holds only the pending-write buffer and a read-only mirror of the last-known
            // Transactions page — both rebuildable — so a destructive rebuild on a schema bump is
            // cheaper than a migration and, at worst, drops unpushed cash entries + a stale cache
            // the next online load restores. (Matches the siblings' read-mirror policy.)
            .fallbackToDestructiveMigration()
            .build()

    @Provides
    fun provideCashEntryDao(db: MagpieDatabase): CashEntryDao = db.cashEntryDao()

    @Provides
    fun provideTransactionCacheDao(db: MagpieDatabase): TransactionCacheDao =
        db.transactionCacheDao()
}
