import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppColors {
  static const blue = Color(0xFF2979FF);
  static const blueLight = Color(0xFFEEF4FF);
  static const blueLighter = Color(0xFFF5F8FF);
  static const violet = Color(0xFF2D00C8);
  static const violetLight = Color(0xFFEDEBFF);
  static const mid = Color(0xFF5B4EE8);
  static const orange = Color(0xFFF04E12);
  static const orangeLight = Color(0xFFFFF0EB);
  static const bg = Color(0xFFF4F6FB);
  static const surface = Color(0xFFFFFFFF);
  static const border = Color(0xFFE6EAF4);
  static const border2 = Color(0xFFCDD4EA);
  static const text = Color(0xFF0F1535);
  static const text2 = Color(0xFF3B4568);
  static const muted = Color(0xFF7A88B2);
  static const dim = Color(0xFFA8B4D0);
  static const green = Color(0xFF0AB87A);
  static const greenLight = Color(0xFFEDFAF4);
  static const red = Color(0xFFE03131);
  static const yellow = Color(0xFFF59F00);
  static const yellowLight = Color(0xFFFFF9DB);

  static const gradientPrimary = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [violet, blue],
  );

  static const gradientOrange = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [orange, Color(0xFFC83C0A)],
  );
}

class AppTheme {
  static ThemeData get theme => ThemeData(
        scaffoldBackgroundColor: AppColors.bg,
        colorScheme: ColorScheme.fromSeed(
          seedColor: AppColors.blue,
          surface: AppColors.surface,
        ),
        textTheme: GoogleFonts.soraTextTheme().apply(
          bodyColor: AppColors.text,
          displayColor: AppColors.text,
        ),
        useMaterial3: true,
      );

  static TextStyle get serif => GoogleFonts.instrumentSerif(
        color: AppColors.text,
      );
}
