let socket;
let audioContext;
let isMuted = false;
let micStream;
let audioWorkletNode;

const clientWaveform = WaveSurfer.create({
  container: '#client-waveform',
  waveColor: 'cyan',
  progressColor: 'deepskyblue',
  height: 100,
  barWidth: 2
});

const agentWaveform = WaveSurfer.create({
  container: '#agent-waveform',
  waveColor: 'lime',
  progressColor: 'green',
  height: 100,
  barWidth: 2
});

function openWebSocket() {
  socket = new WebSocket("wss://pvc66t9j-8080.inc1.devtunnels.ms/voice_chat");
  socket.binaryType = "arraybuffer";

  socket.onopen = () => {
    document.getElementById("status").innerHTML = "Status: <span class='text-green-500 font-semibold'>Connected</span>";
  };

  socket.onclose = () => {
    document.getElementById("status").innerHTML = "Status: <span class='text-red-500 font-semibold'>Disconnected</span>";
  };

  socket.onerror = (error) => {
    document.getElementById("status").innerHTML = "Status: <span class='text-red-500 font-semibold'>Error</span>";
    console.error("WebSocket Error:", error);
  };

  socket.onmessage = async (event) => {
    const audioBlob = new Blob([event.data], { type: "audio/wav" });
    const audioURL = URL.createObjectURL(audioBlob);
    agentWaveform.load(audioURL);
    new Audio(audioURL).play();
  };
}

async function startAudioStream() {
  const startBtn = document.getElementById("start");
  const stopBtn = document.getElementById("stop");
  startBtn.disabled = true;
  stopBtn.disabled = false;

  if (!socket || socket.readyState === WebSocket.CLOSED) {
    openWebSocket();
    await new Promise(resolve => setTimeout(resolve, 500));
  }

  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({
      type: "start_conversation",
      user_id: userId
    }));
  }

  micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  audioContext = new AudioContext();

  await audioContext.audioWorklet.addModule(URL.createObjectURL(new Blob([`
    class PCMWorkletProcessor extends AudioWorkletProcessor {
      process(inputs) {
        const input = inputs[0][0];
        if (!input) return true;

        const pcm = new Int16Array(input.length);
        for (let i = 0; i < input.length; i++) {
          let s = Math.max(-1, Math.min(1, input[i]));
          pcm[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        this.port.postMessage(pcm.buffer, [pcm.buffer]);
        return true;
      }
    }
    registerProcessor('pcm-worklet', PCMWorkletProcessor);
  `], { type: "application/javascript" })));

  const micSource = audioContext.createMediaStreamSource(micStream);
  audioWorkletNode = new AudioWorkletNode(audioContext, 'pcm-worklet');

  audioWorkletNode.port.onmessage = (event) => {
    if (!isMuted && socket && socket.readyState === WebSocket.OPEN) {
      socket.send(event.data);
    }
  };

  micSource.connect(audioWorkletNode).connect(audioContext.destination);

  document.getElementById("status").innerHTML = "Status: <span class='text-blue-500 font-semibold'>Live</span>";
}

function stopAudioStream() {
  const startBtn = document.getElementById("start");
  const stopBtn = document.getElementById("stop");
  startBtn.disabled = false;
  stopBtn.disabled = true;

  if (audioWorkletNode) {
    audioWorkletNode.disconnect();
    audioWorkletNode = null;
  }

  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }

  if (micStream) {
    micStream.getTracks().forEach(track => track.stop());
    micStream = null;
  }

  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "end_conversation" }));
  }

  document.getElementById("status").innerHTML = "Status: <span class='text-gray-400 font-semibold'>Idle</span>";
}

document.getElementById("start").onclick = startAudioStream;
document.getElementById("stop").onclick = stopAudioStream;

document.getElementById("mute").onclick = () => {
  isMuted = !isMuted;
  const muteBtn = document.getElementById("mute");
  muteBtn.innerHTML = isMuted
    ? `<i data-lucide="mic" class="w-5 h-5"></i> Unmute`
    : `<i data-lucide="mic-off" class="w-5 h-5"></i> Mute`;
  muteBtn.classList.toggle("bg-gray-500");
  muteBtn.classList.toggle("bg-yellow-500");
  lucide.createIcons();
};

document.getElementById("start").disabled = false;
document.getElementById("stop").disabled = true;
lucide.createIcons();
