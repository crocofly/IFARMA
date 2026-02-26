import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'theme/app_theme.dart';
import 'services/app_state.dart';
import 'screens/dashboard_screen.dart';

void main() {
  runApp(const IFarmaApp());
}

class IFarmaApp extends StatelessWidget {
  const IFarmaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => AppState(),
      child: MaterialApp(
        title: 'iFarma · Генератор Синопсиса',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.theme,
        home: const DashboardScreen(),
      ),
    );
  }
}
