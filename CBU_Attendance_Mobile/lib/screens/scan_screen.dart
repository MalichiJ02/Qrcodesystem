import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../services/api_service.dart';
import '../utils/formatters.dart';

class ScanScreen extends StatefulWidget {
  final ApiService api;
  final VoidCallback onAttendanceRecorded;

  const ScanScreen({
    required this.api,
    required this.onAttendanceRecorded,
    super.key,
  });

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  final MobileScannerController _scanner = MobileScannerController(
    detectionSpeed: DetectionSpeed.noDuplicates,
    facing: CameraFacing.back,
  );
  final TextEditingController _manualController = TextEditingController();
  bool _submitting = false;
  bool _torch = false;

  Future<void> _submitRaw(String raw) async {
    if (_submitting) return;
    final token = extractAttendanceToken(raw);
    if (token.isEmpty) {
      _showResult(false, 'No attendance token was found in that QR code.');
      return;
    }

    setState(() => _submitting = true);
    await _scanner.stop();
    try {
      final result = await widget.api.checkIn(token);
      final attendance = result['attendance'] as Map<String, dynamic>?;
      final message = result['message']?.toString() ?? 'Attendance recorded.';
      await _showResult(
        true,
        message,
        details: attendance == null
            ? null
            : '${attendance['course_code']} · ${attendance['course_name']}\n${formatDateTime(attendance['recorded_at'])}',
      );
      widget.onAttendanceRecorded();
    } on ApiException catch (e) {
      await _showResult(false, e.message);
    } catch (_) {
      await _showResult(false, 'Could not contact the attendance server.');
    } finally {
      if (mounted) {
        setState(() => _submitting = false);
        await _scanner.start();
      }
    }
  }

  Future<void> _showResult(bool success, String message, {String? details}) async {
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        icon: Icon(
          success ? Icons.check_circle : Icons.error_outline,
          size: 52,
          color: success ? Colors.green : Theme.of(context).colorScheme.error,
        ),
        title: Text(success ? 'Attendance recorded' : 'Check-in failed'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(message, textAlign: TextAlign.center),
            if (details != null) ...[
              const SizedBox(height: 12),
              Text(details, textAlign: TextAlign.center),
            ],
          ],
        ),
        actions: [
          FilledButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Done'),
          ),
        ],
      ),
    );
  }

  Future<void> _manualTokenDialog() async {
    _manualController.clear();
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (context) => Padding(
        padding: EdgeInsets.fromLTRB(
          20,
          20,
          20,
          MediaQuery.of(context).viewInsets.bottom + 20,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Manual token', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            const Text('Use this only when the camera cannot scan the lecturer QR.'),
            const SizedBox(height: 16),
            TextField(
              controller: _manualController,
              autofocus: true,
              decoration: const InputDecoration(
                labelText: 'Session token or QR URL',
                prefixIcon: Icon(Icons.key),
              ),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: () {
                final value = _manualController.text;
                Navigator.pop(context);
                _submitRaw(value);
              },
              child: const Text('Register attendance'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    _scanner.dispose();
    _manualController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        MobileScanner(
          controller: _scanner,
          onDetect: (capture) {
            for (final barcode in capture.barcodes) {
              final value = barcode.rawValue;
              if (value != null && value.trim().isNotEmpty) {
                _submitRaw(value);
                break;
              }
            }
          },
        ),
        Positioned.fill(
          child: IgnorePointer(
            child: CustomPaint(painter: _ScanOverlayPainter()),
          ),
        ),
        Positioned(
          left: 16,
          right: 16,
          top: 16,
          child: Card(
            color: Colors.black87,
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Text(
                _submitting
                    ? 'Registering attendance...'
                    : 'Point the camera at the lecturer\'s active attendance QR code.',
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white),
              ),
            ),
          ),
        ),
        Positioned(
          left: 16,
          right: 16,
          bottom: 20,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              FloatingActionButton.extended(
                heroTag: 'torch',
                onPressed: () async {
                  await _scanner.toggleTorch();
                  setState(() => _torch = !_torch);
                },
                icon: Icon(_torch ? Icons.flash_on : Icons.flash_off),
                label: const Text('Torch'),
              ),
              FloatingActionButton.extended(
                heroTag: 'manual',
                onPressed: _manualTokenDialog,
                icon: const Icon(Icons.keyboard),
                label: const Text('Enter token'),
              ),
            ],
          ),
        ),
        if (_submitting)
          const Positioned.fill(
            child: ColoredBox(
              color: Color(0x55000000),
              child: Center(child: CircularProgressIndicator()),
            ),
          ),
      ],
    );
  }
}

class _ScanOverlayPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final side = size.width * 0.72;
    final rect = Rect.fromCenter(
      center: Offset(size.width / 2, size.height / 2),
      width: side,
      height: side,
    );
    final paint = Paint()
      ..color = Colors.white
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3;
    canvas.drawRRect(RRect.fromRectAndRadius(rect, const Radius.circular(20)), paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
