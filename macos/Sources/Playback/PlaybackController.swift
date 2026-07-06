import AVFoundation
import Foundation

final class PlaybackController: NSObject, ObservableObject, AVAudioPlayerDelegate {
    @Published var isPlaying = false
    @Published var currentTime: TimeInterval = 0
    @Published var duration: TimeInterval = 0

    private var player: AVAudioPlayer?

    deinit {
        player?.delegate = nil
        player?.stop()
    }

    func load(audioURL: URL) throws {
        player?.delegate = nil
        player?.stop()
        let player = try AVAudioPlayer(contentsOf: audioURL)
        player.delegate = self
        player.prepareToPlay()
        self.player = player
        currentTime = 0
        duration = player.duration
        isPlaying = false
    }

    func togglePlayPause() {
        guard let player else { return }

        if player.isPlaying {
            player.pause()
            isPlaying = false
        } else {
            isPlaying = player.play()
        }
        syncTime()
    }

    func seek(by offset: TimeInterval) {
        guard let player else { return }

        let nextTime = min(max(player.currentTime + offset, 0), duration)
        player.currentTime = nextTime
        currentTime = nextTime
    }

    func seek(toProgress progress: Double) {
        guard let player, duration > 0 else { return }

        let clampedProgress = min(max(progress, 0), 1)
        let nextTime = duration * clampedProgress
        player.currentTime = nextTime
        currentTime = nextTime
    }

    func syncTime() {
        guard let player else { return }
        currentTime = player.currentTime
        isPlaying = player.isPlaying
    }

    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        player.currentTime = 0
        currentTime = 0
        isPlaying = false
    }

    func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        isPlaying = false
    }
}
