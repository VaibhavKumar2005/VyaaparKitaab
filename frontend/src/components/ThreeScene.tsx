import { useEffect, useRef } from 'react';

export function ThreeScene() {
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let mounted = true;
    let animationFrame = 0;
    let cleanup: (() => void) | undefined;

    void import('three').then((THREE) => {
      if (!mounted || !hostRef.current) return;

      const scene = new THREE.Scene();
      scene.fog = new THREE.Fog(0x020617, 4, 16);

      const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
      camera.position.set(0, 0.45, 6.5);

      const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setClearColor(0x000000, 0);
      hostRef.current.innerHTML = '';
      hostRef.current.appendChild(renderer.domElement);

      const group = new THREE.Group();
      scene.add(group);

      const core = new THREE.Mesh(
        new THREE.IcosahedronGeometry(1.1, 2),
        new THREE.MeshStandardMaterial({ color: 0x7dd3fc, roughness: 0.25, metalness: 0.45, emissive: 0x102a43, emissiveIntensity: 0.65 }),
      );
      group.add(core);

      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(1.85, 0.08, 16, 120),
        new THREE.MeshStandardMaterial({ color: 0x8b5cf6, roughness: 0.3, metalness: 0.7 }),
      );
      ring.rotation.x = Math.PI * 0.35;
      group.add(ring);

      const secondaryRing = ring.clone();
      (secondaryRing.material as THREE.MeshStandardMaterial).color.setHex(0x38bdf8);
      secondaryRing.rotation.y = Math.PI * 0.5;
      group.add(secondaryRing);

      const particles = new THREE.BufferGeometry();
      const particleCount = 180;
      const positions = new Float32Array(particleCount * 3);
      for (let index = 0; index < particleCount; index += 1) {
        const radius = 3.1 + Math.random() * 3.3;
        const angle = Math.random() * Math.PI * 2;
        const height = (Math.random() - 0.5) * 4.1;
        positions[index * 3] = Math.cos(angle) * radius;
        positions[index * 3 + 1] = height;
        positions[index * 3 + 2] = Math.sin(angle) * radius;
      }
      particles.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      const cloud = new THREE.Points(particles, new THREE.PointsMaterial({ color: 0xe0f2fe, size: 0.045, transparent: true, opacity: 0.8 }));
      group.add(cloud);

      scene.add(new THREE.DirectionalLight(0xffffff, 1.2));
      scene.add(new THREE.AmbientLight(0x60a5fa, 1.5));

      const resize = () => {
        if (!hostRef.current) return;
        const { clientWidth, clientHeight } = hostRef.current;
        renderer.setSize(clientWidth, clientHeight, false);
        camera.aspect = clientWidth / clientHeight;
        camera.updateProjectionMatrix();
      };

      resize();
      window.addEventListener('resize', resize);

      const animate = (time: number) => {
        const elapsed = time * 0.001;
        group.rotation.y = elapsed * 0.35;
        group.rotation.x = Math.sin(elapsed * 0.3) * 0.12;
        core.rotation.x += 0.004;
        ring.rotation.z += 0.0025;
        secondaryRing.rotation.x -= 0.0022;
        cloud.rotation.y -= 0.0012;
        renderer.render(scene, camera);
        animationFrame = window.requestAnimationFrame(animate);
      };

      animationFrame = window.requestAnimationFrame(animate);
      cleanup = () => {
        window.removeEventListener('resize', resize);
        renderer.dispose();
      };
    });

    return () => {
      mounted = false;
      window.cancelAnimationFrame(animationFrame);
      cleanup?.();
    };
  }, []);

  return <div ref={hostRef} className="h-[320px] w-full rounded-[2rem] border border-white/10 bg-slate-950/35" />;
}