import React from 'react';

export const Button: React.FC<any> = (props) => {
  return <div className="button">{props.children}</div>;
};
