package app.where2ski.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import app.where2ski.data.Latest
import app.where2ski.data.Repository
import app.where2ski.data.SettingsStore
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class MainViewModel(app: Application) : AndroidViewModel(app) {
    private val repository = Repository(app)
    val settings = SettingsStore(app)

    private val _latest = MutableStateFlow<Latest?>(null)
    val latest: StateFlow<Latest?> = _latest

    private val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error

    private val _selectedDay = MutableStateFlow(0)
    val selectedDay: StateFlow<Int> = _selectedDay

    init {
        viewModelScope.launch {
            _latest.value = repository.loadCached()
            refresh()
        }
    }

    fun refresh() {
        viewModelScope.launch {
            _loading.value = true
            repository.refresh()
                .onSuccess { _latest.value = it; _error.value = null }
                .onFailure { _error.value = it.message ?: it.toString() }
            _loading.value = false
        }
    }

    fun selectDay(index: Int) {
        _selectedDay.value = index
    }
}
