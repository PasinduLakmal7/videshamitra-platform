import React from 'react';

export const Navbar: React.FC<any> = (props) => {
  return <div className="navbar">{props.children}</div>;
};
