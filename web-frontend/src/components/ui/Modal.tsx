import React from 'react';

export const Modal: React.FC<any> = (props) => {
  return <div className="modal">{props.children}</div>;
};
