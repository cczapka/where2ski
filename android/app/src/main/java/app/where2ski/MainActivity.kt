package app.where2ski

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import app.where2ski.ui.Where2skiApp
import app.where2ski.ui.Where2skiTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            Where2skiTheme {
                Where2skiApp()
            }
        }
    }
}
