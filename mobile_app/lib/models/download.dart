class Download {
  final int id;
  final String name;
  final int status;
  final double percentDone;
  final int totalSize;
  final int downloadedEver;
  final int rateDownload;
  final int eta;
  final int error;
  final String errorString;
  final bool isFinished;
  final int doneDate;
  final String? chatId;
  final int? msgId;

  Download({
    required this.id,
    required this.name,
    required this.status,
    required this.percentDone,
    required this.totalSize,
    required this.downloadedEver,
    required this.rateDownload,
    required this.eta,
    required this.error,
    required this.errorString,
    required this.isFinished,
    required this.doneDate,
    this.chatId,
    this.msgId,
  });

  factory Download.fromJson(Map<String, dynamic> json) => Download(
        id: json['id'] ?? 0,
        name: json['name'] ?? '',
        status: json['status'] ?? 0,
        percentDone: (json['percentDone'] ?? 0.0).toDouble(),
        totalSize: json['totalSize'] ?? 0,
        downloadedEver: json['downloadedEver'] ?? 0,
        rateDownload: json['rateDownload'] ?? 0,
        eta: json['eta'] ?? -1,
        error: json['error'] ?? 0,
        errorString: json['errorString'] ?? '',
        isFinished: json['isFinished'] ?? false,
        doneDate: json['doneDate'] ?? 0,
        chatId: json['chatId'],
        msgId: json['msgId'],
      );

  // Status constants
  static const int stopped = 0;
  static const int checkWait = 1;
  static const int check = 2;
  static const int downloadWait = 3;
  static const int downloading = 4;
  static const int seedWait = 5;
  static const int seeding = 6;

  // Helper getters
  bool get isActive => status == downloading || status == downloadWait;
  bool get isPaused => status == stopped && !isFinished && error == 0;
  bool get hasError => error > 0;
  bool get isCompleted =>
      status == seeding || (status == stopped && isFinished);
}
