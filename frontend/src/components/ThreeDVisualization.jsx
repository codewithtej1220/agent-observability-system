import React, { useRef, useEffect, useState } from 'react';
import * as THREE from 'three';
import gsap from 'gsap';
import './ThreeDVisualization.css';

const ThreeDVisualization = ({ traces = [] }) => {
  const mountRef = useRef(null);
  const canvasRef = useRef(null);
  const sceneRef = useRef(null);
  const cameraRef = useRef(null);
  const rendererRef = useRef(null);
  const particlesRef = useRef([]);
  const pulseRingsRef = useRef([]);
  const rigRef = useRef(null);
  const animationIdRef = useRef(null);
  const clockRef = useRef(new THREE.Clock());
  
  const [isRotating, setIsRotating] = useState(true);
  const [azimuth, setAzimuth] = useState(0);
  const [elevation, setElevation] = useState(0.22);
  const [isDragging, setIsDragging] = useState(false);
  const [lastMouse, setLastMouse] = useState({ x: 0, y: 0 });
  const [hudStats, setHudStats] = useState({
    nodes: 0,
    anomalies: 0,
    scanTime: '00:00:00'
  });

  // Utility: Create soft radial glow texture for nodes
  const makeGlowTexture = (hex) => {
    const size = 128;
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = size;
    const ctx = canvas.getContext('2d');
    const color = new THREE.Color(hex);
    const r = Math.floor(color.r * 255);
    const g = Math.floor(color.g * 255);
    const b = Math.floor(color.b * 255);
    
    const gradient = ctx.createRadialGradient(size/2, size/2, 0, size/2, size/2, size/2);
    gradient.addColorStop(0, `rgba(${r},${g},${b},1)`);
    gradient.addColorStop(0.35, `rgba(${r},${g},${b},0.55)`);
    gradient.addColorStop(1, `rgba(${r},${g},${b},0)`);
    
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, size, size);
    
    return new THREE.CanvasTexture(canvas);
  };

  useEffect(() => {
    if (!mountRef.current || !canvasRef.current) return;

    // Scene setup
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x05070c, 0.045);

    // Camera
    const camera = new THREE.PerspectiveCamera(
      50,
      mountRef.current.clientWidth / mountRef.current.clientHeight,
      0.1,
      200
    );
    camera.position.set(0, 6, 22);

    // Renderer
    const renderer = new THREE.WebGLRenderer({ 
      canvas: canvasRef.current,
      antialias: true,
      alpha: true 
    });
    renderer.setSize(mountRef.current.clientWidth, mountRef.current.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    sceneRef.current = scene;
    cameraRef.current = camera;
    rendererRef.current = renderer;

    // Create rig (group) to hold all elements for unified rotation
    const rig = new THREE.Group();
    scene.add(rig);
    rigRef.current = rig;

    // Floor grid (radar-style)
    const grid = new THREE.GridHelper(34, 22, 0x2a3550, 0x161d2c);
    grid.position.y = -6;
    rig.add(grid);

    // Create glow textures
    const blueGlow = makeGlowTexture(0x5b8cff);
    const papayaGlow = makeGlowTexture(0xff7a1a);

    // Create particles (nodes) from traces
    const createParticles = () => {
      // Clear existing particles
      particlesRef.current.forEach(node => {
        if (node.sprite) rig.remove(node.sprite);
      });
      particlesRef.current = [];
      
      // Clear pulse rings
      pulseRingsRef.current.forEach(p => {
        rig.remove(p.ring);
      });
      pulseRingsRef.current = [];

      const nodeCount = Math.min(traces.length, 42);
      let anomalyCount = 0;
      
      for (let i = 0; i < nodeCount; i++) {
        const trace = traces[i] || { is_anomalous: false, combined_score: 0 };
        const anomalous = trace.is_anomalous;
        if (anomalous) anomalyCount++;
        
        // Position in cylindrical space (radar-style)
        const radius = 4 + Math.random() * 9;
        const theta = Math.random() * Math.PI * 2;
        const y = (Math.random() - 0.3) * 8;
        
        const pos = new THREE.Vector3(
          Math.cos(theta) * radius,
          y,
          Math.sin(theta) * radius
        );

        // Create sprite with glow texture
        const material = new THREE.SpriteMaterial({
          map: anomalous ? papayaGlow : blueGlow,
          transparent: true,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        });
        
        const sprite = new THREE.Sprite(material);
        const scale = anomalous ? 1.6 : 0.9 + Math.random() * 0.5;
        sprite.scale.set(scale, scale, 1);
        sprite.position.copy(pos);
        rig.add(sprite);

        particlesRef.current.push({
          sprite,
          anomalous,
          basePos: pos.clone(),
          phase: Math.random() * Math.PI * 2,
          baseScale: scale
        });

        // Add pulse rings for anomalous nodes
        if (anomalous) {
          const ringGeom = new THREE.RingGeometry(1, 1.05, 32);
          const ringMat = new THREE.MeshBasicMaterial({
            color: 0xff7a1a,
            transparent: true,
            opacity: 0.6,
            side: THREE.DoubleSide,
            blending: THREE.AdditiveBlending,
          });
          const ring = new THREE.Mesh(ringGeom, ringMat);
          ring.position.copy(pos);
          ring.lookAt(camera.position);
          rig.add(ring);
          
          pulseRingsRef.current.push({
            ring,
            t: Math.random()
          });
        }
      }

      // Create connecting lines between nearby nodes
      const lineGeom = new THREE.BufferGeometry();
      const linePositions = [];
      const lineColors = [];
      const tmpColorBlue = new THREE.Color(0x5b8cff);
      const tmpColorPapaya = new THREE.Color(0xff7a1a);

      for (let i = 0; i < particlesRef.current.length; i++) {
        for (let j = i + 1; j < particlesRef.current.length; j++) {
          const d = particlesRef.current[i].basePos.distanceTo(particlesRef.current[j].basePos);
          if (d < 5.5 && Math.random() < 0.5) {
            const p1 = particlesRef.current[i].basePos;
            const p2 = particlesRef.current[j].basePos;
            linePositions.push(p1.x, p1.y, p1.z, p2.x, p2.y, p2.z);
            
            const c = (particlesRef.current[i].anomalous || particlesRef.current[j].anomalous) 
              ? tmpColorPapaya 
              : tmpColorBlue;
            lineColors.push(c.r, c.g, c.b, c.r, c.g, c.b);
          }
        }
      }
      
      if (linePositions.length > 0) {
        lineGeom.setAttribute('position', new THREE.Float32BufferAttribute(linePositions, 3));
        lineGeom.setAttribute('color', new THREE.Float32BufferAttribute(lineColors, 3));
        const lineMat = new THREE.LineBasicMaterial({
          vertexColors: true,
          transparent: true,
          opacity: 0.16,
          blending: THREE.AdditiveBlending,
        });
        const lines = new THREE.LineSegments(lineGeom, lineMat);
        rig.add(lines);
      }

      // Update HUD stats with animation
      setHudStats(prev => ({
        ...prev,
        nodes: nodeCount,
        anomalies: anomalyCount
      }));
    };

    createParticles();

    // Animation loop
    const animate = () => {
      animationIdRef.current = requestAnimationFrame(animate);
      const t = clockRef.current.getElapsedTime();

      // Update scan time
      const formatClock = (sec) => {
        const h = String(Math.floor(sec / 3600)).padStart(2, '0');
        const m = String(Math.floor((sec % 3600) / 60)).padStart(2, '0');
        const s = String(Math.floor(sec % 60)).padStart(2, '0');
        return `${h}:${m}:${s}`;
      };
      setHudStats(prev => ({
        ...prev,
        scanTime: formatClock(t)
      }));

      // Auto-rotate camera
      if (isRotating) {
        setAzimuth(prev => prev + 0.0026);
      }

      // Update camera position based on azimuth and elevation
      camera.position.x = Math.sin(azimuth) * 22 * Math.cos(elevation);
      camera.position.z = Math.cos(azimuth) * 22 * Math.cos(elevation);
      camera.position.y = 6 + elevation * 14;
      camera.lookAt(0, -1, 0);

      // Pulse anomalous nodes
      particlesRef.current.forEach((node) => {
        if (!node.anomalous) return;
        const s = node.baseScale + Math.sin(t * 2.4 + node.phase) * 0.35;
        node.sprite.scale.set(s, s, 1);
      });

      // Expanding detection rings
      pulseRingsRef.current.forEach((p) => {
        p.t += 0.012;
        if (p.t > 1) p.t = 0;
        const scale = 1 + p.t * 3.2;
        p.ring.scale.set(scale, scale, scale);
        p.ring.material.opacity = 0.55 * (1 - p.t);
        p.ring.lookAt(camera.position);
      });

      renderer.render(scene, camera);
    };

    animate();

    // Mouse interaction for drag-to-orbit
    const handlePointerDown = (e) => {
      setIsDragging(true);
      setLastMouse({ x: e.clientX, y: e.clientY });
    };

    const handlePointerUp = () => {
      setIsDragging(false);
    };

    const handlePointerMove = (e) => {
      if (!isDragging) return;
      const dx = e.clientX - lastMouse.x;
      const dy = e.clientY - lastMouse.y;
      
      setAzimuth(prev => prev + dx * 0.005);
      setElevation(prev => Math.max(-0.6, Math.min(0.9, prev + dy * 0.003)));
      setLastMouse({ x: e.clientX, y: e.clientY });
    };

    canvasRef.current.addEventListener('pointerdown', handlePointerDown);
    window.addEventListener('pointerup', handlePointerUp);
    window.addEventListener('pointermove', handlePointerMove);

    // Handle resize
    const handleResize = () => {
      if (!mountRef.current) return;
      
      camera.aspect = mountRef.current.clientWidth / mountRef.current.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(mountRef.current.clientWidth, mountRef.current.clientHeight);
    };

    window.addEventListener('resize', handleResize);

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize);
      if (canvasRef.current) {
        canvasRef.current.removeEventListener('pointerdown', handlePointerDown);
      }
      window.removeEventListener('pointerup', handlePointerUp);
      window.removeEventListener('pointermove', handlePointerMove);
      
      if (animationIdRef.current) {
        cancelAnimationFrame(animationIdRef.current);
      }
      renderer.dispose();
    };
  }, [traces, isRotating, azimuth, elevation, isDragging, lastMouse]);

  return (
    <div className="three-d-container viz-panel">
      <div className="three-d-header panel-head">
        <h3 className="three-d-title panel-title">
          <svg viewBox="0 0 24 24" fill="none" className="title-icon">
            <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5"/>
            <path d="M3 12h18M12 3c2.5 2.7 4 6 4 9s-1.5 6.3-4 9c-2.5-2.7-4-6-4-9s1.5-6.3 4-9z" stroke="currentColor" strokeWidth="1.5"/>
          </svg>
          3D Trace Visualization
        </h3>
        <button 
          className={`ghost-btn ${isRotating ? 'active' : ''}`}
          onClick={() => setIsRotating(!isRotating)}
          data-active={isRotating}
        >
          <svg viewBox="0 0 24 24" fill="none" id="rotateIcon">
            {isRotating ? (
              <path d="M8 5v14l11-7z" fill="currentColor"/>
            ) : (
              <>
                <rect x="6" y="5" width="4" height="14" fill="currentColor"/>
                <rect x="14" y="5" width="4" height="14" fill="currentColor"/>
              </>
            )}
          </svg>
          <span id="rotateLabel">{isRotating ? 'Rotate' : 'Paused'}</span>
        </button>
      </div>
      
      <div className="legend">
        <span className="legend-item">
          <i className="dot dot-blue"></i>
          Normal Traces
        </span>
        <span className="legend-item">
          <i className="dot dot-papaya"></i>
          Anomalous Traces
        </span>
      </div>
      
      <div className="viz-frame" ref={mountRef}>
        <canvas ref={canvasRef} id="traceCanvas" />
        
        {/* HUD Overlay */}
        <div className="hud" aria-hidden="true">
          <span className="hud-corner tl"></span>
          <span className="hud-corner tr"></span>
          <span className="hud-corner bl"></span>
          <span className="hud-corner br"></span>
          <div className="hud-sweep"></div>
          
          <div className="hud-readout hud-tl">
            <span>NODES <b id="hudNodes">{hudStats.nodes}</b></span>
          </div>
          <div className="hud-readout hud-tr">
            <span>ANOMALY <b id="hudAnomaly" className="papaya-text">{hudStats.anomalies}</b></span>
          </div>
          <div className="hud-readout hud-bl">
            <span>SCAN <b id="hudScan">{hudStats.scanTime}</b></span>
          </div>
        </div>
      </div>
      
      <p className="viz-caption">
        Interactive 3D visualization of agent execution traces<br/>
        <em>Anomalies pulse on scan contact · drag to orbit · lines show trace relationships</em>
      </p>
    </div>
  );
};

export default ThreeDVisualization;
