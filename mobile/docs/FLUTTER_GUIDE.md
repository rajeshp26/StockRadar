# Flutter Mobile App Guide

This guide provides a streamlined, step-by-step process for launching the Flutter mobile app.

## 1. Backend Configuration

The Flutter app communicates with the backend API. Ensure the backend is running and accessible. The standard configuration is:

- **Backend Port**: `8001`

## 2. Environment Variables

The Flutter app is configured using Dart's `--dart-define` feature. These variables are essential for the app to connect to the correct backend and Firebase project.

- `BACKEND_URL`: The full URL of the backend API. For local development, this is `http://localhost:8001`.
- `FIREBASE_PROJECT_ID`: The project ID of your Firebase project.

## 3. Launching the App

To run the Flutter app, use the following command from the project's root directory:

```bash
flutter run --dart-define=BACKEND_URL=http://localhost:8001 --dart-define=FIREBASE_PROJECT_ID=your-firebase-project-id
```

Replace `your-firebase-project-id` with your actual Firebase project ID.

This command will build and launch the app on your connected device or emulator, with the necessary environment variables to connect to the backend and Firebase.
