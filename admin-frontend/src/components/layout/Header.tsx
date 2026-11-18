import React from 'react';

export const Header: React.FC<any> = (props) => {
  return <div className="header">{props.children}</div>;
};
