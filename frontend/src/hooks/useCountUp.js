// useCountUp.js - GSAP count-up animation hook
import { useEffect, useRef } from 'react';
import gsap from 'gsap';

export const useCountUp = (value, duration = 1.4) => {
  const elementRef = useRef(null);
  const animationRef = useRef(null);

  useEffect(() => {
    if (!elementRef.current || value === undefined) return;

    const obj = { val: 0 };
    
    animationRef.current = gsap.to(obj, {
      val: value,
      duration: duration,
      ease: 'power2.out',
      onUpdate: () => {
        if (elementRef.current) {
          elementRef.current.textContent = Math.floor(obj.val);
        }
      },
    });

    return () => {
      if (animationRef.current) {
        animationRef.current.kill();
      }
    };
  }, [value, duration]);

  return elementRef;
};

export const useCountUpFloat = (value, decimals = 1, suffix = '', duration = 1.4) => {
  const elementRef = useRef(null);
  const animationRef = useRef(null);

  useEffect(() => {
    if (!elementRef.current || value === undefined) return;

    const obj = { val: 0 };
    
    animationRef.current = gsap.to(obj, {
      val: value,
      duration: duration,
      ease: 'power2.out',
      onUpdate: () => {
        if (elementRef.current) {
          elementRef.current.textContent = obj.val.toFixed(decimals) + suffix;
        }
      },
    });

    return () => {
      if (animationRef.current) {
        animationRef.current.kill();
      }
    };
  }, [value, decimals, suffix, duration]);

  return elementRef;
};
