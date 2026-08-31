const statusEl = document.getElementById('status');
const btn = document.getElementById('healthBtn');
const artScene = document.getElementById('art-scene');

async function checkHealth() {
  try {
    const res = await fetch('/health');
    const data = await res.json();
    statusEl.textContent = `Backend status: ${data.status}`;
  } catch (err) {
    statusEl.textContent = `Backend status: error (${err.message})`;
  }
}

btn.addEventListener('click', checkHealth);
checkHealth();

async function initScene() {
  if (!artScene) {
    return;
  }

  const THREE = await import('https://cdn.jsdelivr.net/npm/three@0.161.0/build/three.module.js');

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x07111f, 4, 15);

  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  camera.position.set(0, 0.4, 6.5);

  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x000000, 0);
  artScene.appendChild(renderer.domElement);

  const group = new THREE.Group();
  scene.add(group);

  const coreGeometry = new THREE.IcosahedronGeometry(1.15, 2);
  const coreMaterial = new THREE.MeshStandardMaterial({
    color: 0x7dd3fc,
    roughness: 0.25,
    metalness: 0.45,
    emissive: 0x102a43,
    emissiveIntensity: 0.6,
    flatShading: false,
  });
  const core = new THREE.Mesh(coreGeometry, coreMaterial);
  group.add(core);

  const ringGeometry = new THREE.TorusGeometry(1.9, 0.08, 16, 120);
  const ringMaterial = new THREE.MeshStandardMaterial({
    color: 0x38bdf8,
    roughness: 0.3,
    metalness: 0.7,
  });
  const ringOne = new THREE.Mesh(ringGeometry, ringMaterial);
  ringOne.rotation.x = Math.PI * 0.35;
  group.add(ringOne);

  const ringTwo = new THREE.Mesh(ringGeometry, ringMaterial.clone());
  ringTwo.material.color.setHex(0xa78bfa);
  ringTwo.rotation.y = Math.PI * 0.5;
  ringTwo.rotation.z = Math.PI * 0.28;
  group.add(ringTwo);

  const particles = new THREE.BufferGeometry();
  const particleCount = 220;
  const particlePositions = new Float32Array(particleCount * 3);
  for (let i = 0; i < particleCount; i += 1) {
    const radius = 3.2 + Math.random() * 3.5;
    const angle = Math.random() * Math.PI * 2;
    const height = (Math.random() - 0.5) * 4.2;
    particlePositions[i * 3] = Math.cos(angle) * radius;
    particlePositions[i * 3 + 1] = height;
    particlePositions[i * 3 + 2] = Math.sin(angle) * radius;
  }
  particles.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));

  const particleMaterial = new THREE.PointsMaterial({
    color: 0xe0f2fe,
    size: 0.045,
    transparent: true,
    opacity: 0.85,
  });
  const particleCloud = new THREE.Points(particles, particleMaterial);
  group.add(particleCloud);

  const lightOne = new THREE.DirectionalLight(0xffffff, 1.2);
  lightOne.position.set(4, 6, 5);
  scene.add(lightOne);

  const lightTwo = new THREE.AmbientLight(0x60a5fa, 1.6);
  scene.add(lightTwo);

  const resize = () => {
    const { clientWidth, clientHeight } = artScene;
    renderer.setSize(clientWidth, clientHeight, false);
    camera.aspect = clientWidth / clientHeight;
    camera.updateProjectionMatrix();
  };

  resize();
  window.addEventListener('resize', resize);

  let lastTime = 0;
  const animate = (time) => {
    const elapsed = time * 0.001;
    const delta = elapsed - lastTime;
    lastTime = elapsed;

    group.rotation.y += delta * 0.35;
    group.rotation.x = Math.sin(elapsed * 0.35) * 0.15;
    core.rotation.x += delta * 0.5;
    core.rotation.z += delta * 0.35;
    ringOne.rotation.z += delta * 0.2;
    ringTwo.rotation.x += delta * 0.17;
    particleCloud.rotation.y -= delta * 0.08;

    renderer.render(scene, camera);
    requestAnimationFrame(animate);
  };

  requestAnimationFrame(animate);
}

initScene().catch((error) => {
  if (artScene) {
    artScene.classList.add('scene-fallback');
    artScene.textContent = 'Abstract visual unavailable';
  }
  console.error('Three.js scene failed to load:', error);
});
