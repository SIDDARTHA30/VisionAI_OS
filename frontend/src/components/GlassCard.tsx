import React from 'react';
import { motion } from 'framer-motion';

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}

export const GlassCard: React.FC<GlassCardProps> = ({ children, className = '', delay = 0 }) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: 'easeOut', delay }}
      whileHover={{ y: -2 }}
      className={`glass-panel rounded-2xl p-6 backdrop-blur-md transition-all duration-300 ${className}`}
    >
      {children}
    </motion.div>
  );
};
