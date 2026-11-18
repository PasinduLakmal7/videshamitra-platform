import React from 'react';

export const Sidebar: React.FC<any> = (props) => {
  return <div className="sidebar">{props.children}</div>;
};
