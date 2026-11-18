import React from 'react';

export const Card: React.FC<any> = (props) => {
  return <div className="card">{props.children}</div>;
};
