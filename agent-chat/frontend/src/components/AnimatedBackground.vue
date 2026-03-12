<template>
  <div class="animated-background">
    <canvas ref="canvas" class="particles-canvas"></canvas>
    <div class="gradient-overlay"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';

const canvas = ref(null);
let ctx = null;
let particles = [];
let animationId = null;

class Particle {
  constructor(x, y) {
    this.x = x;
    this.y = y;
    this.size = Math.random() * 2 + 1;
    this.speedX = Math.random() * 0.5 - 0.25;
    this.speedY = Math.random() * 0.5 - 0.25;
    this.opacity = Math.random() * 0.5 + 0.2;
  }

  update() {
    this.x += this.speedX;
    this.y += this.speedY;

    if (this.x > canvas.value.width) this.x = 0;
    if (this.x < 0) this.x = canvas.value.width;
    if (this.y > canvas.value.height) this.y = 0;
    if (this.y < 0) this.y = canvas.value.height;
  }

  draw() {
    ctx.fillStyle = `rgba(0, 119, 204, ${this.opacity * 0.6})`;
    ctx.beginPath();
    ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
    ctx.fill();
  }
}

function initParticles() {
  particles = [];
  const particleCount = Math.floor((canvas.value.width * canvas.value.height) / 15000);

  for (let i = 0; i < particleCount; i++) {
    particles.push(
      new Particle(
        Math.random() * canvas.value.width,
        Math.random() * canvas.value.height
      )
    );
  }
}

function connectParticles() {
  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const dx = particles[i].x - particles[j].x;
      const dy = particles[i].y - particles[j].y;
      const distance = Math.sqrt(dx * dx + dy * dy);

      if (distance < 120) {
        ctx.strokeStyle = `rgba(0, 119, 204, ${0.12 * (1 - distance / 120)})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(particles[i].x, particles[i].y);
        ctx.lineTo(particles[j].x, particles[j].y);
        ctx.stroke();
      }
    }
  }
}

function animate() {
  ctx.clearRect(0, 0, canvas.value.width, canvas.value.height);

  particles.forEach(particle => {
    particle.update();
    particle.draw();
  });

  connectParticles();
  animationId = requestAnimationFrame(animate);
}

function resizeCanvas() {
  canvas.value.width = window.innerWidth;
  canvas.value.height = window.innerHeight;
  initParticles();
}

onMounted(() => {
  ctx = canvas.value.getContext('2d');
  resizeCanvas();
  animate();

  window.addEventListener('resize', resizeCanvas);
});

onUnmounted(() => {
  if (animationId) {
    cancelAnimationFrame(animationId);
  }
  window.removeEventListener('resize', resizeCanvas);
});
</script>

<style scoped>
.animated-background {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  pointer-events: none;
}

.particles-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

.gradient-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: radial-gradient(
    ellipse at 30% 20%,
    rgba(0, 119, 204, 0.06) 0%,
    transparent 55%
  ),
  radial-gradient(
    ellipse at 70% 80%,
    rgba(99, 102, 241, 0.04) 0%,
    transparent 50%
  );
}
</style>
