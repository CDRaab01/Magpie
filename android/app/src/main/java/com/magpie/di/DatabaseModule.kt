package com.magpie.di

import android.content.Context
import androidx.room.Room
import com.magpie.data.local.db.CashEntryDao
import com.magpie.data.local.db.MagpieDatabase
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
            // The DB is only a pending-write buffer here (no read cache yet) — a rebuild on
            // schema bump is cheaper than a migration and only loses unpushed offline entries.
            .fallbackToDestructiveMigration()
            .build()

    @Provides
    fun provideCashEntryDao(db: MagpieDatabase): CashEntryDao = db.cashEntryDao()
}
