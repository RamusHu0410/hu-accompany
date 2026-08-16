import 'package:flutter/material.dart';

/// Placeholder shelf. Nothing is actually stored here yet — this is where
/// searched/downloaded scores will land once that wiring exists. For now
/// it's just an interactive grid of empty slots you can tap.
class Shelf_Page extends StatelessWidget {
  const Shelf_Page({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF2A2018),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text(
          'Shelf',
          style: TextStyle(color: Color(0xFFEDE6DA), letterSpacing: 2, fontSize: 14),
        ),
        iconTheme: const IconThemeData(color: Color(0xFFEDE6DA)),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: GridView.builder(
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 3,
              mainAxisSpacing: 16,
              crossAxisSpacing: 16,
              childAspectRatio: 0.68,
            ),
            itemCount: 12,
            itemBuilder: (context, i) => const _ShelfSlot(),
          ),
        ),
      ),
    );
  }
}

class _ShelfSlot extends StatelessWidget {
  const _ShelfSlot();

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Nothing stored here yet'),
            duration: Duration(milliseconds: 900),
          ),
        );
      },
      child: Container(
        decoration: BoxDecoration(
          color: const Color(0xFF3A2E22),
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.3),
              blurRadius: 6,
              offset: const Offset(0, 3),
            ),
          ],
        ),
        child: Center(
          child: Icon(
            Icons.music_note_rounded,
            color: Colors.white.withValues(alpha: 0.12),
            size: 22,
          ),
        ),
      ),
    );
  }
}